"""CRUD + denormalized-field maintenance for the sources table."""

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.models import IngestionJob, Source

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Create / get-or-create
# ---------------------------------------------------------------------------

async def create_source(db: AsyncSession, **kwargs: Any) -> Source:
    """Get-or-create a source keyed by (type, url). Race-safe via UPSERT."""
    src_type = kwargs.get("type")
    url = kwargs.get("url")
    if not (src_type and url):
        # Fall back to plain INSERT for callers that omit the unique pair.
        source = Source(**kwargs)
        db.add(source)
        await db.flush()
        await db.refresh(source)
        return source

    # Map Python attr names → actual DB column names for on_conflict set_.
    mutable_keys = {
        "region": "region", "brand": "brand", "kb_target": "kb_target",
        "language": "language", "metadata_": "metadata", "origin": "origin",
    }
    update_set = {
        col: kwargs[attr] for attr, col in mutable_keys.items()
        if attr in kwargs and kwargs[attr] is not None
    }

    stmt = pg_insert(Source).values(**kwargs)
    if update_set:
        stmt = stmt.on_conflict_do_update(
            constraint="uq_sources_type_url",
            set_=update_set,
        )
    else:
        stmt = stmt.on_conflict_do_nothing(constraint="uq_sources_type_url")
    stmt = stmt.returning(Source.id)

    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        # ON CONFLICT DO NOTHING + race; fetch existing
        existing = await get_source_by_url(db, url, type=src_type)
        if existing is None:
            raise RuntimeError(f"Source upsert failed for ({src_type}, {url})")
        return existing

    source = await db.get(Source, row[0])
    await db.flush()
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
# List with pagination — flat read, no joins
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
    language: str | None = None,
    search: str | None = None,
    origin: str | None = None,
    include_discovered_pending: bool = False,
) -> dict:
    """List sources, defaulting to manual + already-confirmed discovered.

    Discovered sources still in needs_confirmation state are hidden from the
    main listing — they belong on the review page (queried separately).
    """
    query = select(Source)
    count_query = select(func.count()).select_from(Source)

    def _apply(stmt):
        if type is not None:
            stmt = stmt.where(Source.type == type)
        if status is not None:
            stmt = stmt.where(Source.status == status)
        if region is not None:
            stmt = stmt.where(Source.region == region)
        if brand is not None:
            stmt = stmt.where(Source.brand == brand)
        if kb_target is not None:
            stmt = stmt.where(Source.kb_target == kb_target)
        if language is not None:
            stmt = stmt.where(Source.language == language)
        if origin is not None:
            stmt = stmt.where(Source.origin == origin)
        if not include_discovered_pending:
            stmt = stmt.where(
                ~((Source.origin == "discovered") & (Source.status == "needs_confirmation"))
            )
        if search is not None:
            pattern = f"%{search}%"
            stmt = stmt.where(
                Source.url.ilike(pattern)
                | Source.metadata_["nav_label"].astext.ilike(pattern)
            )
        return stmt

    query = _apply(query)
    count_query = _apply(count_query)

    total = (await db.execute(count_query)).scalar_one()
    offset = (page - 1) * size
    query = query.offset(offset).limit(size).order_by(Source.created_at.desc())

    result = await db.execute(query)
    items = list(result.scalars().all())
    pages = math.ceil(total / size) if size > 0 else 0

    return {"items": items, "total": total, "page": page, "size": size, "pages": pages}


async def list_sources_pending_review(
    db: AsyncSession, *, page: int = 1, size: int = 20,
) -> dict:
    """List discovered sources awaiting human confirmation."""
    base = select(Source).where(
        Source.origin == "discovered", Source.status == "needs_confirmation",
    )
    count_q = select(func.count()).select_from(Source).where(
        Source.origin == "discovered", Source.status == "needs_confirmation",
    )
    total = (await db.execute(count_q)).scalar_one()
    offset = (page - 1) * size
    rows = (await db.execute(
        base.order_by(Source.created_at.desc()).offset(offset).limit(size),
    )).scalars().all()
    return {
        "items": list(rows), "total": total, "page": page, "size": size,
        "pages": math.ceil(total / size) if size > 0 else 0,
    }


# ---------------------------------------------------------------------------
# Run history (timestamps only — for source detail page)
# ---------------------------------------------------------------------------

async def get_run_history(
    db: AsyncSession, source_id: uuid.UUID, *, limit: int = 50,
) -> list[dict]:
    """Return ingestion run history for a source — timestamps + final status only."""
    stmt = (
        select(
            IngestionJob.id,
            IngestionJob.status,
            IngestionJob.started_at,
            IngestionJob.completed_at,
        )
        .where(IngestionJob.source_id == source_id)
        .order_by(IngestionJob.started_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [
        {"id": r.id, "status": r.status, "started_at": r.started_at, "completed_at": r.completed_at}
        for r in result.all()
    ]


# ---------------------------------------------------------------------------
# Cross-filtered facet counts
# ---------------------------------------------------------------------------

async def get_filter_counts(
    db: AsyncSession,
    *,
    type: str | None = None,
    status: str | None = None,
    region: str | None = None,
    brand: str | None = None,
    kb_target: str | None = None,
    origin: str | None = None,
    search: str | None = None,
) -> dict:
    """Compute cross-filtered counts for each filter dimension."""

    def _apply(stmt, *, exclude: str | None = None):
        if exclude != "type" and type is not None:
            stmt = stmt.where(Source.type == type)
        if exclude != "status" and status is not None:
            stmt = stmt.where(Source.status == status)
        if exclude != "region" and region is not None:
            stmt = stmt.where(Source.region == region)
        if exclude != "brand" and brand is not None:
            stmt = stmt.where(Source.brand == brand)
        if exclude != "kb_target" and kb_target is not None:
            stmt = stmt.where(Source.kb_target == kb_target)
        if exclude != "origin" and origin is not None:
            stmt = stmt.where(Source.origin == origin)
        if exclude != "search" and search is not None:
            pattern = f"%{search}%"
            stmt = stmt.where(Source.url.ilike(pattern))
        # Always hide discovered-pending from main listing facets
        stmt = stmt.where(
            ~((Source.origin == "discovered") & (Source.status == "needs_confirmation"))
        )
        return stmt

    status_stmt = _apply(select(Source.status, func.count()).group_by(Source.status), exclude="status")
    region_stmt = _apply(select(Source.region, func.count()).group_by(Source.region), exclude="region")
    brand_stmt = _apply(select(Source.brand, func.count()).group_by(Source.brand), exclude="brand")
    origin_stmt = _apply(select(Source.origin, func.count()).group_by(Source.origin), exclude="origin")

    by_status = {row[0]: row[1] for row in (await db.execute(status_stmt)).all()}
    by_region = {row[0]: row[1] for row in (await db.execute(region_stmt)).all() if row[0] is not None}
    by_brand = {row[0]: row[1] for row in (await db.execute(brand_stmt)).all() if row[0] is not None}
    by_origin = {row[0]: row[1] for row in (await db.execute(origin_stmt)).all()}

    return {
        "by_status": by_status,
        "by_region": by_region,
        "by_brand": by_brand,
        "by_origin": by_origin,
    }


# ---------------------------------------------------------------------------
# Update — generic + denormalized-field setters
# ---------------------------------------------------------------------------

async def update_source(
    db: AsyncSession, source_id: uuid.UUID, **kwargs: Any,
) -> Source | None:
    if not kwargs:
        return await get_source(db, source_id)
    stmt = (
        update(Source)
        .where(Source.id == source_id)
        .values(**kwargs)
        .returning(Source.id)
    )
    result = await db.execute(stmt)
    if result.first() is None:
        return None
    return await get_source(db, source_id)


async def set_display_status(
    db: AsyncSession, source_id: uuid.UUID, display_status: str,
) -> None:
    await db.execute(
        update(Source).where(Source.id == source_id).values(display_status=display_status)
    )


async def set_active_job(
    db: AsyncSession, source_id: uuid.UUID, job_id: uuid.UUID | None,
) -> None:
    await db.execute(
        update(Source).where(Source.id == source_id).values(active_job_id=job_id)
    )


async def set_active_file(
    db: AsyncSession, source_id: uuid.UUID, file_id: uuid.UUID | None,
) -> None:
    await db.execute(
        update(Source).where(Source.id == source_id).values(active_file_id=file_id)
    )


async def dismiss_source(db: AsyncSession, source_id: uuid.UUID) -> Source | None:
    return await update_source(
        db, source_id, status="dismissed", display_status="idle",
    )


async def mark_ingested(db: AsyncSession, source_id: uuid.UUID) -> Source | None:
    """Mark a source as having a completed ingestion run."""
    return await update_source(
        db, source_id,
        status="ingested",
        display_status="idle",
        active_job_id=None,
    )


async def mark_failed(db: AsyncSession, source_id: uuid.UUID) -> Source | None:
    return await update_source(
        db, source_id,
        status="failed",
        display_status="failed",
        active_job_id=None,
    )


async def mark_scouted(
    db: AsyncSession, source_id: uuid.UUID, scout_summary: dict,
) -> Source | None:
    return await update_source(db, source_id, scout_summary=scout_summary)


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
