"""Background queue worker — claims queue items and runs full pipeline.

Concurrency is controlled by an asyncio.Semaphore sized to MAX_CONCURRENT_JOBS.
Each claimed item runs in its own asyncio.Task under that semaphore.  A periodic
heartbeat keeps processing items from going stale, and a sweep task reclaims
items whose heartbeat has expired (e.g. after a crash).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kb_manager.config import get_settings
from kb_manager.queries import queue as queue_queries
from kb_manager.queries import sources as source_queries
from kb_manager.queries import jobs as job_queries
from kb_manager.services.pipeline import Pipeline
from kb_manager.services.stream_manager import StreamManager

logger = logging.getLogger(__name__)

# How often to update heartbeat for a processing item (seconds)
_HEARTBEAT_INTERVAL = 30


class QueueWorker:
    """Background worker that processes queue items with bounded concurrency."""

    def __init__(
        self,
        pipeline: Pipeline,
        stream_manager: StreamManager,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._pipeline = pipeline
        self._stream = stream_manager
        self._session_factory = session_factory
        self._notify_event = asyncio.Event()
        self._tasks: set[asyncio.Task] = set()
        self._loop_task: asyncio.Task | None = None
        self._stale_task: asyncio.Task | None = None

        settings = get_settings()
        self._semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_JOBS)
        self._poll_interval = settings.QUEUE_POLL_INTERVAL
        self._stale_timeout = settings.QUEUE_STALE_TIMEOUT
        self._retry_base_delay = settings.QUEUE_RETRY_BASE_DELAY
        self._max_workers = settings.MAX_CONCURRENT_JOBS

    def start(self) -> None:
        self._loop_task = asyncio.create_task(self._run_loop(), name="queue-worker-loop")
        self._stale_task = asyncio.create_task(self._stale_sweep_loop(), name="queue-stale-sweep")
        logger.info("🏭 Queue worker started — max_concurrent=%d, poll=%ds, stale_timeout=%ds",
                     self._max_workers, self._poll_interval, self._stale_timeout)

    def stop(self) -> None:
        if self._loop_task:
            self._loop_task.cancel()
        if self._stale_task:
            self._stale_task.cancel()
        for task in self._tasks:
            task.cancel()
        logger.info("🏭 Queue worker stopped")

    def notify(self) -> None:
        """Wake the poll loop immediately (called after POST /queue)."""
        self._notify_event.set()

    @property
    def active_count(self) -> int:
        """Number of items currently being processed."""
        return self._max_workers - self._semaphore._value

    # ------------------------------------------------------------------
    # Main poll loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        while True:
            try:
                # Wait for a semaphore slot before even trying to claim
                await self._semaphore.acquire()

                try:
                    async with self._session_factory() as db:
                        item = await queue_queries.claim_next(db)
                        await db.commit()
                except Exception:
                    self._semaphore.release()
                    raise

                if item is None:
                    # Nothing to claim — release slot and wait
                    self._semaphore.release()
                    self._notify_event.clear()
                    try:
                        await asyncio.wait_for(
                            self._notify_event.wait(),
                            timeout=self._poll_interval,
                        )
                    except asyncio.TimeoutError:
                        pass
                    continue

                # Spawn a task for this item (semaphore slot already held)
                worker_id = self._max_workers - self._semaphore._value - 1
                task = asyncio.create_task(
                    self._process_item_wrapper(item, worker_id),
                    name=f"queue-item-{str(item.id)[:8]}",
                )
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("🏭 Queue worker loop error: %s", exc)
                # Release semaphore if we acquired it before the error
                try:
                    self._semaphore.release()
                except ValueError:
                    pass
                await asyncio.sleep(self._poll_interval)

    async def _process_item_wrapper(self, item, worker_id: int) -> None:
        """Wrapper that ensures semaphore release and heartbeat cleanup."""
        heartbeat_task = None
        try:
            heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(item.id),
                name=f"heartbeat-{str(item.id)[:8]}",
            )
            await self._process_item(item, worker_id)
        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
            self._semaphore.release()

    async def _heartbeat_loop(self, item_id: uuid.UUID) -> None:
        """Periodically update heartbeat for a processing item."""
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
            try:
                async with self._session_factory() as db:
                    await queue_queries.update_heartbeat(db, item_id)
                    await db.commit()
            except Exception as exc:
                logger.warning("🏭 Heartbeat update failed for %s: %s", str(item_id)[:8], exc)

    # ------------------------------------------------------------------
    # Stale item recovery
    # ------------------------------------------------------------------

    async def _stale_sweep_loop(self) -> None:
        """Periodically check for stale processing items and reclaim them."""
        while True:
            try:
                await asyncio.sleep(self._stale_timeout // 2)
                async with self._session_factory() as db:
                    reclaimed = await queue_queries.reclaim_stale(db, self._stale_timeout)
                    await db.commit()
                if reclaimed:
                    logger.warning("♻️ Reclaimed %d stale queue items", len(reclaimed))
                    for info in reclaimed:
                        await self._stream.publish_event(
                            "queue", "item_reclaimed",
                            queue_item_id=str(info["id"]),
                            url=info["url"],
                            worker_id=None,
                        )
                    self._notify_event.set()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("🏭 Stale sweep error: %s", exc)

    # ------------------------------------------------------------------
    # Process a single item
    # ------------------------------------------------------------------

    async def _process_item(self, item, worker_id: int) -> None:
        t0 = time.perf_counter()
        item_id = item.id
        url = item.url
        logger.info("🏭 [w%d][queue=%s] Processing: %s", worker_id, str(item_id)[:8], url)

        await self._stream.publish_event(
            "worker", "worker_started",
            worker_id=worker_id,
            queue_item_id=str(item_id),
            url=url,
        )

        try:
            async with self._session_factory() as db:
                source = await source_queries.create_source(
                    db,
                    type="aem",
                    url=url,
                    region=item.region,
                    brand=item.brand,
                    kb_target=item.kb_target,
                )
                job = await job_queries.create_job(db, source_id=source.id, status="scouting")
                await db.commit()
                job_id = job.id

            await self._stream.publish_event(
                "progress", "phase_changed",
                worker_id=worker_id,
                queue_item_id=str(item_id),
                phase="scouting",
                progress_pct=15,
                job_id=str(job_id),
            )

            # run_scout auto-advances to run_process at end.
            # Note: run_scout/run_process never raise on pipeline failures —
            # they catch and call _fail_job. So after this returns we must
            # inspect the job's final status and mirror it onto the queue item.
            await self._pipeline.run_scout(job_id, url)

            async with self._session_factory() as db:
                job = await job_queries.get_job(db, job_id)
                job_status = job.status if job is not None else None
                job_error = job.error_message if job is not None else None

                if job_status == "failed":
                    result = await queue_queries.mark_failed(
                        db, item_id,
                        job_error or f"Job {str(job_id)[:8]} failed without error message",
                        retry_base_delay=self._retry_base_delay,
                    )
                    await db.commit()
                    elapsed = (time.perf_counter() - t0) * 1000
                    outcome = result["outcome"]
                    logger.warning(
                        "⚠️ [w%d][queue=%s] Job failure (%s) in %.1fms: %s",
                        worker_id, str(item_id)[:8], outcome, elapsed,
                        (job_error or "")[:120],
                    )
                    event_data = {
                        "worker_id": worker_id,
                        "queue_item_id": str(item_id),
                        "job_id": str(job_id),
                        "url": url,
                        "error": job_error,
                        **result,
                    }
                    await self._stream.publish_event(
                        "queue",
                        "item_failed" if outcome == "failed" else "item_requeued",
                        data=event_data,
                    )
                    if outcome == "requeued":
                        self._notify_event.set()
                    return

                await queue_queries.mark_completed(db, item_id, job_id=job_id)
                await db.commit()

            elapsed = (time.perf_counter() - t0) * 1000
            logger.info("✅ [w%d][queue=%s] Completed in %.1fms", worker_id, str(item_id)[:8], elapsed)

            await self._stream.publish_event(
                "queue", "item_completed",
                worker_id=worker_id,
                queue_item_id=str(item_id),
                job_id=str(job_id),
                url=url,
                elapsed_ms=round(elapsed, 1),
            )

        except Exception as exc:
            logger.exception("💥 [w%d][queue=%s] Failed: %s", worker_id, str(item_id)[:8], exc)
            try:
                async with self._session_factory() as db:
                    result = await queue_queries.mark_failed(
                        db, item_id, str(exc),
                        retry_base_delay=self._retry_base_delay,
                    )
                    await db.commit()
                outcome = result["outcome"]
                event_data = {
                    "worker_id": worker_id,
                    "queue_item_id": str(item_id),
                    "url": url,
                    "error": str(exc),
                    **result,
                }
                await self._stream.publish_event(
                    "queue",
                    "item_failed" if outcome == "failed" else "item_requeued",
                    data=event_data,
                )
                if outcome == "requeued":
                    self._notify_event.set()
            except Exception as inner_exc:
                logger.exception("💥 [w%d][queue=%s] Failed to mark failure: %s",
                                 worker_id, str(item_id)[:8], inner_exc)
        finally:
            await self._stream.publish_event(
                "worker", "worker_idle",
                worker_id=worker_id,
            )
