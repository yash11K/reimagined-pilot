"""CRUD for queue_items — keyed by source_id; rows DELETED on terminal state."""

import logging
import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.models import QueueItem

logger = logging.getLogger(__name__)


async def add_to_queue(
    db: AsyncSession,
    source_id: uuid.UUID,
    *,
    priority: int = 0,
    max_retries: int = 3,
    job_id: uuid.UUID | None = None,
) -> QueueItem | None:
    """Insert a queue row for `source_id`; skip if one is already active.

    Returns the new item, or None if a duplicate active row already exists
    (uq_queue_active_source partial unique index handles concurrency).
    """
    values: dict = {
        "source_id": source_id,
        "priority": priority,
        "max_retries": max_retries,
    }
    if job_id is not None:
        values["job_id"] = job_id

    # Try a plain INSERT, catch unique-violation by pre-checking; the partial
    # unique index can't be referenced by ON CONFLICT, so fall through manually.
    existing = await get_active_queue_item_for_source(db, source_id)
    if existing is not None:
        logger.info("♻️ Queue skip (already active): source=%s", str(source_id)[:8])
        return None

    item = QueueItem(**values)
    db.add(item)
    await db.flush()
    logger.info("📥 Queue item added: id=%s, source=%s",
                str(item.id)[:8], str(source_id)[:8])
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


async def claim_next(db: AsyncSession, worker_id: int | None = None) -> QueueItem | None:
    """Atomically claim the oldest queued item, respecting backoff + priority."""
    now = datetime.now(timezone.utc)
    stmt = (
        select(QueueItem)
        .where(
            QueueItem.status == "queued",
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
        item.worker_id = worker_id
        await db.flush()
        logger.info("🔒 Queue item claimed: id=%s", str(item.id)[:8])
    return item


async def update_heartbeat(db: AsyncSession, item_id: uuid.UUID) -> None:
    await db.execute(
        update(QueueItem)
        .where(QueueItem.id == item_id)
        .values(last_heartbeat=datetime.now(timezone.utc))
    )


async def mark_completed(db: AsyncSession, item_id: uuid.UUID) -> None:
    """Delete the queue row — completion lives on the job, not the queue."""
    await db.execute(delete(QueueItem).where(QueueItem.id == item_id))


async def mark_failed(
    db: AsyncSession,
    item_id: uuid.UUID,
    error: str,
    retry_base_delay: int = 5,
) -> dict:
    """If retries remain, requeue with backoff. Else delete the row."""
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

    retry_count, max_retries = item.retry_count, item.max_retries
    await db.execute(delete(QueueItem).where(QueueItem.id == item_id))
    return {"outcome": "failed", "retry_count": retry_count, "max_retries": max_retries}


async def reclaim_stale(db: AsyncSession, stale_timeout: int = 300) -> list[dict]:
    """Find processing items with stale heartbeats and requeue them."""
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
    to_delete: list[uuid.UUID] = []
    for item in stale_items:
        if item.retry_count < item.max_retries:
            item.retry_count += 1
            item.status = "queued"
            item.error_message = f"Reclaimed: stale heartbeat (>{stale_timeout}s)"
            item.started_at = None
            item.last_heartbeat = None
            item.next_attempt_at = datetime.now(timezone.utc)
            reclaimed.append({"id": item.id, "source_id": item.source_id})
            logger.warning("♻️ Reclaimed stale item: id=%s", str(item.id)[:8])
        else:
            to_delete.append(item.id)
            logger.warning("💀 Stale item exhausted retries: id=%s", str(item.id)[:8])

    if to_delete:
        await db.execute(delete(QueueItem).where(QueueItem.id.in_(to_delete)))
    if reclaimed or to_delete:
        await db.flush()
    return reclaimed


async def get_queue_position(db: AsyncSession, source_id: uuid.UUID) -> int | None:
    """Position in queue for a source — count of items strictly ahead."""
    item = await get_active_queue_item_for_source(db, source_id)
    if item is None or item.status != "queued":
        return None

    count_stmt = (
        select(func.count())
        .select_from(QueueItem)
        .where(
            QueueItem.status == "queued",
            QueueItem.id != item.id,
            sa.or_(
                QueueItem.priority > item.priority,
                and_(
                    QueueItem.priority == item.priority,
                    QueueItem.created_at < item.created_at,
                ),
            ),
        )
    )
    return (await db.execute(count_stmt)).scalar_one()


async def get_active_queue_item_for_source(
    db: AsyncSession, source_id: uuid.UUID,
) -> QueueItem | None:
    stmt = (
        select(QueueItem)
        .where(
            QueueItem.source_id == source_id,
            QueueItem.status.in_(["queued", "processing"]),
        )
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_active_queue_items_batch(
    db: AsyncSession, source_ids: list[uuid.UUID],
) -> dict[uuid.UUID, QueueItem]:
    if not source_ids:
        return {}
    stmt = (
        select(QueueItem)
        .where(
            QueueItem.source_id.in_(source_ids),
            QueueItem.status.in_(["queued", "processing"]),
        )
        .order_by(QueueItem.status.desc())  # 'processing' > 'queued' lexically
    )
    by_source: dict[uuid.UUID, QueueItem] = {}
    for item in (await db.execute(stmt)).scalars().all():
        if item.source_id not in by_source:
            by_source[item.source_id] = item
    return by_source


async def get_queue_counts(db: AsyncSession) -> dict[str, int]:
    stmt = select(QueueItem.status, func.count()).group_by(QueueItem.status)
    counts = {row[0]: row[1] for row in (await db.execute(stmt)).all()}
    return {
        "queued": counts.get("queued", 0),
        "processing": counts.get("processing", 0),
    }
