"""CRUD operations for the queue_items table."""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update, func, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.models import QueueItem

logger = logging.getLogger(__name__)


async def add_to_queue(
    db: AsyncSession,
    url: str,
    region: str | None = None,
    brand: str | None = None,
    kb_target: str = "public",
    priority: int = 0,
    max_retries: int = 3,
) -> QueueItem | None:
    """Insert a queue item, skipping if an active item for this URL already exists.

    Returns the item if inserted, None if duplicate was skipped.
    """
    stmt = (
        pg_insert(QueueItem)
        .values(
            url=url,
            region=region,
            brand=brand,
            kb_target=kb_target,
            priority=priority,
            max_retries=max_retries,
        )
        .on_conflict_do_nothing(index_elements=["url"], index_where=QueueItem.status.in_(["queued", "processing"]))
        .returning(QueueItem.__table__.c.id)
    )
    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        logger.info("♻️ Queue skip (duplicate active): %s", url[:80])
        return None

    # Fetch the full ORM object
    item = await db.get(QueueItem, row[0])
    await db.flush()
    logger.info("📥 Queue item added: id=%s, url=%s", str(item.id)[:8], url[:80])
    return item


async def get_queue_items(
    db: AsyncSession,
    status: str | None = None,
    limit: int = 50,
) -> list[QueueItem]:
    stmt = select(QueueItem).order_by(QueueItem.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(QueueItem.status == status)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def claim_next(db: AsyncSession) -> QueueItem | None:
    """Atomically claim the oldest queued item for processing.

    Respects next_attempt_at for retry backoff and priority ordering.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        select(QueueItem)
        .where(
            QueueItem.status == "queued",
            # Only claim items whose retry delay has elapsed
            (QueueItem.next_attempt_at <= now) | (QueueItem.next_attempt_at.is_(None)),
        )
        .order_by(QueueItem.priority.desc(), QueueItem.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()
    if item:
        item.status = "processing"
        item.started_at = now
        item.last_heartbeat = now
        await db.flush()
        logger.info("🔒 Queue item claimed: id=%s, url=%s", str(item.id)[:8], item.url[:80])
    return item


async def update_heartbeat(db: AsyncSession, item_id: uuid.UUID) -> None:
    """Update the heartbeat timestamp for a processing item."""
    await db.execute(
        update(QueueItem)
        .where(QueueItem.id == item_id)
        .values(last_heartbeat=datetime.now(timezone.utc))
    )


async def mark_completed(
    db: AsyncSession,
    item_id: uuid.UUID,
    job_id: uuid.UUID | None = None,
) -> None:
    await db.execute(
        update(QueueItem)
        .where(QueueItem.id == item_id)
        .values(
            status="completed",
            job_id=job_id,
            completed_at=datetime.now(timezone.utc),
        )
    )


async def mark_failed(
    db: AsyncSession,
    item_id: uuid.UUID,
    error: str,
    retry_base_delay: int = 5,
) -> dict:
    """Mark item as failed. If retries remain, requeue with backoff.

    Returns dict with ``outcome`` ("requeued" or "failed") and retry timing.
    """
    item = await db.get(QueueItem, item_id)
    if item is None:
        return {"outcome": "failed"}

    if item.retry_count < item.max_retries:
        item.retry_count += 1
        item.status = "queued"
        item.error_message = error
        delay = retry_base_delay * (2 ** item.retry_count)
        next_attempt = datetime.now(timezone.utc) + timedelta(seconds=delay)
        item.next_attempt_at = next_attempt
        item.started_at = None
        item.last_heartbeat = None
        await db.flush()
        logger.info(
            "🔄 Queue item requeued (retry %d/%d, delay %ds): id=%s",
            item.retry_count, item.max_retries, delay, str(item_id)[:8],
        )
        return {
            "outcome": "requeued",
            "retry_count": item.retry_count,
            "max_retries": item.max_retries,
            "backoff_seconds": delay,
            "next_retry_at": next_attempt.isoformat(),
        }

    item.status = "failed"
    item.error_message = error
    item.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return {"outcome": "failed", "retry_count": item.retry_count, "max_retries": item.max_retries}


async def reclaim_stale(db: AsyncSession, stale_timeout: int = 300) -> list[dict]:
    """Find processing items with stale heartbeats and requeue them.

    Returns list of dicts with ``id`` and ``url`` for reclaimed items.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_timeout)
    stmt = (
        select(QueueItem)
        .where(
            QueueItem.status == "processing",
            QueueItem.last_heartbeat < cutoff,
        )
        .with_for_update(skip_locked=True)
    )
    result = await db.execute(stmt)
    stale_items = list(result.scalars().all())

    reclaimed: list[dict] = []
    for item in stale_items:
        if item.retry_count < item.max_retries:
            item.retry_count += 1
            item.status = "queued"
            item.error_message = f"Reclaimed: stale heartbeat (>{stale_timeout}s)"
            item.started_at = None
            item.last_heartbeat = None
            item.next_attempt_at = datetime.now(timezone.utc)
            reclaimed.append({"id": item.id, "url": item.url})
            logger.warning(
                "♻️ Reclaimed stale item: id=%s, retry %d/%d",
                str(item.id)[:8], item.retry_count, item.max_retries,
            )
        else:
            item.status = "failed"
            item.error_message = f"Failed: stale heartbeat after {item.max_retries} retries"
            item.completed_at = datetime.now(timezone.utc)
            logger.warning("💀 Stale item exhausted retries: id=%s", str(item.id)[:8])

    if reclaimed:
        await db.flush()
    return reclaimed


async def get_queue_counts(db: AsyncSession) -> dict[str, int]:
    stmt = select(QueueItem.status, func.count()).group_by(QueueItem.status)
    result = await db.execute(stmt)
    counts = {row[0]: row[1] for row in result.all()}
    return {
        "queued": counts.get("queued", 0),
        "processing": counts.get("processing", 0),
        "completed": counts.get("completed", 0),
        "failed": counts.get("failed", 0),
    }
