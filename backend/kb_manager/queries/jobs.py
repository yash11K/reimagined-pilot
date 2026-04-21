"""CRUD and status transition queries for the ingestion_jobs table."""

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import case, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from kb_manager.models import IngestionJob, KBFile, Source

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("scouting", "awaiting_confirmation", "processing")


async def create_job(db: AsyncSession, **kwargs: Any) -> IngestionJob:
    """Create a new ingestion job record."""
    job = IngestionJob(**kwargs)
    db.add(job)
    await db.flush()
    await db.refresh(job)
    logger.info("📋 Job created: id=%s, source_id=%s, status=%s",
                str(job.id)[:8], str(job.source_id)[:8], job.status)
    return job


async def get_job(db: AsyncSession, job_id: uuid.UUID) -> IngestionJob | None:
    """Get an ingestion job by ID."""
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
    """List ingestion jobs with pagination and optional filters (legacy signature)."""
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
    """List jobs with source join, discovered_count, and extended filters.

    Parameters
    ----------
    status : str | None
        Comma-separated list of statuses to include (e.g. ``"completed,failed"``).
    brand : str | None
        Filter by source brand.
    sort : str
        ``"<field>:<dir>"`` — supported fields: ``started_at``, ``completed_at``.
    """
    # --- discovered_count subquery (files created under this job) ---
    file_count_sq = (
        select(func.count(KBFile.id))
        .where(KBFile.job_id == IngestionJob.id)
        .correlate(IngestionJob)
        .scalar_subquery()
        .label("discovered_count")
    )

    # --- source_label: coalesce(metadata->>'nav_label', source.url) ---
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

    # --- Filters ---
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

    # --- Sort ---
    sort_col = IngestionJob.started_at
    sort_dir = "desc"
    if sort:
        parts = sort.split(":")
        field = parts[0]
        if len(parts) > 1:
            sort_dir = parts[1]
        if field == "completed_at":
            sort_col = IngestionJob.completed_at

    order = sort_col.desc() if sort_dir == "desc" else sort_col.asc()
    query = query.order_by(order.nulls_last())

    offset = (page - 1) * size
    query = query.offset(offset).limit(size)

    result = await db.execute(query)
    rows = result.all()

    items = []
    for row in rows:
        job = row[0]
        discovered = row[1] or 0
        label = row[2] or ""
        s_type = row[3] or ""
        s_brand = row[4]
        items.append({
            "id": job.id,
            "source_id": job.source_id,
            "source_label": label,
            "source_type": s_type,
            "status": job.status,
            "progress_pct": job.progress_pct,
            "discovered_count": discovered,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "error_message": job.error_message,
            "brand": s_brand,
        })

    pages = math.ceil(total / size) if size > 0 else 0
    return {"items": items, "total": total, "page": page, "size": size, "pages": pages}


async def update_job(
    db: AsyncSession, job_id: uuid.UUID, **kwargs: Any
) -> IngestionJob | None:
    """Update an ingestion job by ID."""
    job = await get_job(db, job_id)
    if job is None:
        return None
    for key, value in kwargs.items():
        setattr(job, key, value)
    await db.flush()
    await db.refresh(job)
    return job


async def update_job_status(
    db: AsyncSession,
    job_id: uuid.UUID,
    status: str,
    *,
    error_message: str | None = None,
) -> IngestionJob | None:
    """Transition a job to a new status, optionally setting error_message and completed_at."""
    job = await get_job(db, job_id)
    if job is None:
        logger.warning("⚠️ Attempted to update status of non-existent job %s", job_id)
        return None
    old_status = job.status
    job.status = status
    if error_message is not None:
        job.error_message = error_message
    if status in ("completed", "failed"):
        job.completed_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(job)
    logger.info("📋 Job %s status: %s → %s%s",
                str(job_id)[:8], old_status, status,
                f" (error: {error_message})" if error_message else "")
    return job


async def delete_job(db: AsyncSession, job_id: uuid.UUID) -> bool:
    """Delete an ingestion job by ID. Returns True if deleted."""
    job = await get_job(db, job_id)
    if job is None:
        return False
    await db.delete(job)
    await db.flush()
    return True


async def get_active_jobs(db: AsyncSession) -> list[IngestionJob]:
    """Get all jobs with active statuses (scouting, awaiting_confirmation, processing)."""
    result = await db.execute(
        select(IngestionJob).where(IngestionJob.status.in_(ACTIVE_STATUSES))
    )
    return list(result.scalars().all())
