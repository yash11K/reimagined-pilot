"""CRUD and status transitions for the ingestion_jobs table.

`run_count` and `last_run_at` on the parent source are kept fresh by DB
triggers — these helpers only update the job row.
"""

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.models import IngestionJob, KBFile, Source

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("scouting", "awaiting_confirmation", "processing")


async def create_job(db: AsyncSession, **kwargs: Any) -> IngestionJob:
    job = IngestionJob(**kwargs)
    db.add(job)
    await db.flush()
    await db.refresh(job)
    logger.info(
        "📋 Job created: id=%s, source_id=%s, status=%s",
        str(job.id)[:8], str(job.source_id)[:8], job.status,
    )
    return job


async def get_job(db: AsyncSession, job_id: uuid.UUID) -> IngestionJob | None:
    result = await db.execute(
        select(IngestionJob).where(IngestionJob.id == job_id)
    )
    return result.scalar_one_or_none()


async def list_jobs(
    db: AsyncSession,
    *,
    page: int = 1,
    size: int = 20,
    status: str | None = None,
    source_id: uuid.UUID | None = None,
) -> dict:
    return await list_jobs_extended(
        db, page=page, size=size, status=status, source_id=source_id,
    )


async def list_jobs_extended(
    db: AsyncSession,
    *,
    page: int = 1,
    size: int = 20,
    status: str | None = None,
    source_id: uuid.UUID | None = None,
    brand: str | None = None,
    sort: str = "started_at:desc",
) -> dict:
    """List jobs joined with source label + brand + file count."""
    file_count_sq = (
        select(func.count(KBFile.id))
        .where(KBFile.job_id == IngestionJob.id)
        .correlate(IngestionJob)
        .scalar_subquery()
        .label("discovered_count")
    )

    source_label_expr = func.coalesce(
        Source.metadata_["nav_label"].astext,
        Source.url,
    ).label("source_label")

    query = (
        select(
            IngestionJob,
            file_count_sq,
            source_label_expr,
            Source.type.label("source_type"),
            Source.brand.label("source_brand"),
        )
        .join(Source, IngestionJob.source_id == Source.id)
    )
    count_query = (
        select(func.count())
        .select_from(IngestionJob)
        .join(Source, IngestionJob.source_id == Source.id)
    )

    if status is not None:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if len(statuses) == 1:
            query = query.where(IngestionJob.status == statuses[0])
            count_query = count_query.where(IngestionJob.status == statuses[0])
        elif statuses:
            query = query.where(IngestionJob.status.in_(statuses))
            count_query = count_query.where(IngestionJob.status.in_(statuses))

    if source_id is not None:
        query = query.where(IngestionJob.source_id == source_id)
        count_query = count_query.where(IngestionJob.source_id == source_id)

    if brand is not None:
        query = query.where(Source.brand == brand)
        count_query = count_query.where(Source.brand == brand)

    total = (await db.execute(count_query)).scalar_one()

    sort_col = IngestionJob.started_at
    sort_dir = "desc"
    if sort:
        parts = sort.split(":")
        if parts[0] == "completed_at":
            sort_col = IngestionJob.completed_at
        if len(parts) > 1:
            sort_dir = parts[1]
    order = sort_col.desc() if sort_dir == "desc" else sort_col.asc()
    query = query.order_by(order.nulls_last())

    offset = (page - 1) * size
    rows = (await db.execute(query.offset(offset).limit(size))).all()

    items = [
        {
            "id": r[0].id,
            "source_id": r[0].source_id,
            "source_label": r[2] or "",
            "source_type": r[3] or "",
            "status": r[0].status,
            "progress_pct": r[0].progress_pct,
            "discovered_count": r[1] or 0,
            "started_at": r[0].started_at,
            "completed_at": r[0].completed_at,
            "error_message": r[0].error_message,
            "brand": r[4],
        }
        for r in rows
    ]

    pages = math.ceil(total / size) if size > 0 else 0
    return {"items": items, "total": total, "page": page, "size": size, "pages": pages}


async def update_job(
    db: AsyncSession, job_id: uuid.UUID, **kwargs: Any,
) -> IngestionJob | None:
    if not kwargs:
        return await get_job(db, job_id)
    stmt = (
        update(IngestionJob)
        .where(IngestionJob.id == job_id)
        .values(**kwargs)
        .returning(IngestionJob.id)
    )
    if (await db.execute(stmt)).first() is None:
        return None
    return await get_job(db, job_id)


async def update_job_status(
    db: AsyncSession,
    job_id: uuid.UUID,
    status: str,
    *,
    error_message: str | None = None,
) -> IngestionJob | None:
    """Transition a job to a new status, optionally setting error_message + completed_at."""
    values: dict[str, Any] = {"status": status}
    if error_message is not None:
        values["error_message"] = error_message
    if status in ("completed", "failed"):
        values["completed_at"] = datetime.now(timezone.utc)
    stmt = (
        update(IngestionJob)
        .where(IngestionJob.id == job_id)
        .values(**values)
        .returning(IngestionJob.id)
    )
    if (await db.execute(stmt)).first() is None:
        logger.warning("⚠️ Tried to update non-existent job %s", job_id)
        return None
    logger.info("📋 Job %s → %s%s",
                str(job_id)[:8], status,
                f" (error: {error_message})" if error_message else "")
    return await get_job(db, job_id)


async def delete_job(db: AsyncSession, job_id: uuid.UUID) -> bool:
    job = await get_job(db, job_id)
    if job is None:
        return False
    await db.delete(job)
    await db.flush()
    return True


async def get_latest_steering_prompt(
    db: AsyncSession, source_id: uuid.UUID,
) -> str | None:
    stmt = (
        select(IngestionJob.steering_prompt)
        .where(
            IngestionJob.source_id == source_id,
            IngestionJob.status.in_(["completed", "failed"]),
        )
        .order_by(IngestionJob.started_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
