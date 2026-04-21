"""CRUD and lifecycle queries for the sources table."""

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.models import IngestionJob, Source

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Create / get-or-create
# ---------------------------------------------------------------------------

async def create_source(db: AsyncSession, **kwargs: Any) -> Source:
    """Get-or-create a source by (type, url).

    If exists, updates mutable fields and returns it.
    """
    src_type = kwargs.get("type")
    url = kwargs.get("url")

    if src_type and url:
        result = await db.execute(
            select(Source).where(Source.type == src_type, Source.url == url)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            for key in ("region", "brand", "kb_target", "metadata_"):
                if key in kwargs and kwargs[key] is not None:
                    setattr(existing, key, kwargs[key])
            await db.flush()
            await db.refresh(existing)
            logger.info("📌 Source reused: id=%s, url=%s", str(existing.id)[:8], existing.url[:60])
            return existing

    source = Source(**kwargs)
    db.add(source)
    await db.flush()
    await db.refresh(source)
    logger.info("📌 Source created: id=%s, url=%s", str(source.id)[:8], source.url[:60])
    return source


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

async def get_source(db: AsyncSession, source_id: uuid.UUID) -> Source | None:
    result = await db.execute(select(Source).where(Source.id == source_id))
    return result.scalar_one_or_none()


async def get_source_by_url(db: AsyncSession, url: str, type: str = "aem") -> Source | None:
    result = await db.execute(
        select(Source).where(Source.type == type, Source.url == url)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# List with pagination
# ---------------------------------------------------------------------------

async def list_sources(
    db: AsyncSession,
    *,
    page: int = 1,
    size: int = 20,
    type: str | None = None,
    status: str | None = None,
    region: str | None = None,
    brand: str | None = None,
    kb_target: str | None = None,
    search: str | None = None,
) -> dict:
    """List sources with pagination, optional filters, and URL search."""
    query = select(Source)
    count_query = select(func.count()).select_from(Source)

    if type is not None:
        query = query.where(Source.type == type)
        count_query = count_query.where(Source.type == type)
    if status is not None:
        query = query.where(Source.status == status)
        count_query = count_query.where(Source.status == status)
    if region is not None:
        query = query.where(Source.region.ilike(f"%{region}%"))
        count_query = count_query.where(Source.region.ilike(f"%{region}%"))
    if brand is not None:
        query = query.where(Source.brand.ilike(f"%{brand}%"))
        count_query = count_query.where(Source.brand.ilike(f"%{brand}%"))
    if kb_target is not None:
        query = query.where(Source.kb_target == kb_target)
        count_query = count_query.where(Source.kb_target == kb_target)
    if search is not None:
        pattern = f"%{search}%"
        query = query.where(Source.url.ilike(pattern))
        count_query = count_query.where(Source.url.ilike(pattern))

    total = (await db.execute(count_query)).scalar_one()
    offset = (page - 1) * size
    query = query.offset(offset).limit(size).order_by(Source.created_at.desc())

    result = await db.execute(query)
    items = list(result.scalars().all())
    pages = math.ceil(total / size) if size > 0 else 0

    return {"items": items, "total": total, "page": page, "size": size, "pages": pages}


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

async def update_source(
    db: AsyncSession, source_id: uuid.UUID, **kwargs: Any,
) -> Source | None:
    source = await get_source(db, source_id)
    if source is None:
        return None
    for key, value in kwargs.items():
        setattr(source, key, value)
    await db.flush()
    await db.refresh(source)
    return source


async def update_source_by_url(
    db: AsyncSession, url: str, type: str = "aem", **kwargs: Any,
) -> Source | None:
    """Update a source identified by (type, url)."""
    source = await get_source_by_url(db, url, type=type)
    if source is None:
        return None
    for key, value in kwargs.items():
        setattr(source, key, value)
    await db.flush()
    await db.refresh(source)
    return source


async def dismiss_source(db: AsyncSession, source_id: uuid.UUID) -> Source | None:
    return await update_source(db, source_id, status="dismissed")


async def mark_ingested(db: AsyncSession, source_id: uuid.UUID) -> Source | None:
    return await update_source(
        db, source_id,
        status="ingested",
        is_ingested=True,
        last_ingested_at=datetime.now(timezone.utc),
    )


async def mark_failed(db: AsyncSession, source_id: uuid.UUID) -> Source | None:
    """Mark a source as failed — used when its ingestion job crashes.

    Leaves the source row intact (so we have an audit trail and can retry),
    but clears `is_ingested` and sets `status='failed'` so downstream logic
    doesn't treat it as successfully processed.
    """
    return await update_source(
        db, source_id,
        status="failed",
        is_ingested=False,
    )


async def mark_scouted(db: AsyncSession, source_id: uuid.UUID, scout_summary: dict) -> Source | None:
    return await update_source(
        db, source_id,
        is_scouted=True,
        scout_summary=scout_summary,
    )


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

async def delete_source(db: AsyncSession, source_id: uuid.UUID) -> bool:
    source = await get_source(db, source_id)
    if source is None:
        return False
    await db.delete(source)
    await db.flush()
    return True


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

async def get_source_job_count(db: AsyncSession, source_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(IngestionJob).where(
            IngestionJob.source_id == source_id,
        )
    )
    return result.scalar_one()
