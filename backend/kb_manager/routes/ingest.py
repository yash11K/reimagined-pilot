"""Ingestion API routes — start ingestion, SSE scout/progress streams, content map."""

import asyncio
import json
import logging
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.database import get_db
from kb_manager.queries import jobs as job_queries
from kb_manager.queries import queue as queue_queries
from kb_manager.queries import sources as source_queries
from kb_manager.schemas.ingest import (
    IngestRequest,
    IngestResponse,
    JobCreated,
)
from kb_manager.services.pipeline import _extract_language

router = APIRouter()
logger = logging.getLogger(__name__)

KEEPALIVE_INTERVAL = 15  # seconds


# ---------------------------------------------------------------------------
# SSE generator
# ---------------------------------------------------------------------------

async def _sse_stream_generator(
    request: Request,
    job_id: uuid.UUID,
    channel: str,
    terminal_event: str,
) -> AsyncGenerator[str, None]:
    stream_manager = request.app.state.stream_manager
    job_id_str = str(job_id)
    queue: asyncio.Queue = asyncio.Queue()
    key = (job_id_str, channel)
    stream_manager._channels[key].append(queue)

    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_INTERVAL)
            except asyncio.TimeoutError:
                yield ":keepalive\n\n"
                continue

            if item is None:
                break

            event_type = item.get("event", "message")
            event_data = json.dumps(item.get("data", {}))
            yield f"event: {event_type}\ndata: {event_data}\n\n"

            if event_type == terminal_event:
                break

    except asyncio.CancelledError:
        logger.info("📡 SSE cancelled: job=%s channel=%s", job_id_str[:8], channel)
    finally:
        subscribers = stream_manager._channels.get(key)
        if subscribers is not None:
            try:
                subscribers.remove(queue)
            except ValueError:
                pass


# ---------------------------------------------------------------------------
# Background task wrappers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# POST /ingest
# ---------------------------------------------------------------------------

@router.post("/ingest", status_code=202, response_model=IngestResponse)
async def start_ingest(
    request: Request,
    ingest_request: IngestRequest,
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    """Start AEM ingestion. Creates source + job per URL, then enqueues each
    URL on the worker queue (pre-bound to its job_id) so processing inherits
    the queue worker's concurrency, retry, heartbeat and graceful-shutdown
    semantics rather than running as a fire-and-forget ``BackgroundTask``.
    Callers receive job_ids immediately for SSE subscription.
    """
    if not ingest_request.urls:
        raise HTTPException(status_code=422, detail="urls required for aem connector")

    created_jobs: list[JobCreated] = []
    for url_input in ingest_request.urls:
        # Normalize: ensure URL ends with .model.json for AEM fetching
        normalized_url = url_input.url
        if not normalized_url.endswith(".model.json"):
            normalized_url = normalized_url.rstrip("/") + ".model.json"

        # Extract language from URL path segments
        language = _extract_language(normalized_url)

        source = await source_queries.create_source(
            db,
            type="aem",
            url=normalized_url,
            region=url_input.region,
            brand=url_input.brand,
            kb_target=ingest_request.kb_target,
            language=language,
            origin="manual",
            metadata_={
                "nav_label": url_input.nav_label,
                "nav_section": url_input.nav_section,
                "page_path": url_input.page_path,
            },
        )

        job = await job_queries.create_job(
            db,
            source_id=source.id,
            status="scouting",
            steering_prompt=ingest_request.steering_prompt,
        )
        await source_queries.set_active_job(db, source.id, job.id)
        await source_queries.set_display_status(db, source.id, "queued")

        await queue_queries.add_to_queue(
            db,
            source_id=source.id,
            job_id=job.id,
        )

        created_jobs.append(JobCreated(
            job_id=job.id,
            source_id=source.id,
            source_url=normalized_url,
            status="scouting",
        ))

    await db.commit()

    # Wake the worker so the queued items start immediately rather than
    # waiting up to QUEUE_POLL_INTERVAL seconds.
    worker = getattr(request.app.state, "queue_worker", None)
    if worker is not None:
        worker.notify()

    return IngestResponse(jobs=created_jobs)


# ---------------------------------------------------------------------------
# GET /ingest/{job_id}/scout-stream
# ---------------------------------------------------------------------------

@router.get("/ingest/{job_id}/scout-stream")
async def scout_stream(
    job_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    job = await job_queries.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return StreamingResponse(
        _sse_stream_generator(request, job_id, "scout", "scout_complete"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# GET /ingest/{job_id}/content-map
# ---------------------------------------------------------------------------

@router.get("/ingest/{job_id}/content-map")
async def get_content_map(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return scout summary after scouting completes."""
    job = await job_queries.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if job.status == "scouting":
        raise HTTPException(status_code=409, detail="Scouting still in progress")

    source = job.source
    scout_summary = source.scout_summary or {"components": [], "expansion_source_ids": [], "summary": {}}

    return {
        "job_id": str(job_id),
        "status": job.status,
        "source_url": source.url,
        "source_id": str(source.id),
        "content_map": scout_summary,
    }


# ---------------------------------------------------------------------------
# GET /ingest/{job_id}/progress-stream
# ---------------------------------------------------------------------------

@router.get("/ingest/{job_id}/progress-stream")
async def progress_stream(
    job_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    job = await job_queries.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return StreamingResponse(
        _sse_stream_generator(request, job_id, "progress", "job_complete"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
