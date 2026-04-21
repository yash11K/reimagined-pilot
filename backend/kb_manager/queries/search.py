"""Global search queries — fan out a single term across files, sources, and jobs."""

import logging

from sqlalchemy import column, exists, func, literal, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.models import IngestionJob, KBFile, Source

logger = logging.getLogger(__name__)


async def search_files(db: AsyncSession, q: str, *, limit: int = 5) -> dict:
    """Search KB files by title, tags, category, and source_url (no content)."""
    pattern = f"%{q}%"

    # Partial match on tags: EXISTS (SELECT 1 FROM unnest(tags) AS t WHERE t ILIKE '%q%')
    tag_elem = column("t")
    tag_match = exists(
        select(literal(1))
        .select_from(func.unnest(KBFile.tags).alias("t"))
        .where(tag_elem.ilike(pattern))
    )

    where_clause = (
        KBFile.title.ilike(pattern)
        | KBFile.category.ilike(pattern)
        | KBFile.source_url.ilike(pattern)
        | tag_match
    )

    total = (await db.execute(
        select(func.count()).select_from(KBFile).where(where_clause),
    )).scalar_one()

    rows = (await db.execute(
        select(KBFile).where(where_clause).order_by(KBFile.created_at.desc()).limit(limit),
    )).scalars().all()

    items = [
        {
            "id": f.id,
            "title": f.title,
            "status": f.status,
            "region": f.region,
            "brand": f.brand,
            "kb_target": f.kb_target,
            "category": f.category,
            "visibility": f.visibility,
            "tags": f.tags,
            "quality_verdict": f.quality_verdict,
            "uniqueness_verdict": f.uniqueness_verdict,
            "source_url": f.source_url,
            "created_at": f.created_at,
        }
        for f in rows
    ]
    return {"items": items, "total": total}


async def search_sources(db: AsyncSession, q: str, *, limit: int = 5) -> dict:
    """Search sources by url, nav_label metadata, brand, and region."""
    pattern = f"%{q}%"

    nav_label_expr = Source.metadata_["nav_label"].astext

    where_clause = (
        Source.url.ilike(pattern)
        | nav_label_expr.ilike(pattern)
        | Source.brand.ilike(pattern)
        | Source.region.ilike(pattern)
    )

    # job_count subquery (reuse pattern from sources list)
    job_count_sq = (
        select(func.count(IngestionJob.id))
        .where(IngestionJob.source_id == Source.id)
        .correlate(Source)
        .scalar_subquery()
        .label("job_count")
    )

    total = (await db.execute(
        select(func.count()).select_from(Source).where(where_clause),
    )).scalar_one()

    rows = (await db.execute(
        select(Source, job_count_sq)
        .where(where_clause)
        .order_by(Source.created_at.desc())
        .limit(limit),
    )).all()

    items = [
        {
            "id": s.id,
            "url": s.url,
            "type": s.type,
            "region": s.region,
            "brand": s.brand,
            "kb_target": s.kb_target,
            "status": s.status,
            "is_scouted": s.is_scouted,
            "is_ingested": s.is_ingested,
            "created_at": s.created_at,
            "job_count": jc or 0,
        }
        for s, jc in rows
    ]
    return {"items": items, "total": total}


async def search_jobs(db: AsyncSession, q: str, *, limit: int = 5) -> dict:
    """Search jobs by source label (nav_label or url) and brand."""
    pattern = f"%{q}%"

    source_label_expr = func.coalesce(
        Source.metadata_["nav_label"].astext,
        Source.url,
    )

    file_count_sq = (
        select(func.count(KBFile.id))
        .where(KBFile.job_id == IngestionJob.id)
        .correlate(IngestionJob)
        .scalar_subquery()
        .label("discovered_count")
    )

    where_clause = (
        source_label_expr.ilike(pattern)
        | Source.brand.ilike(pattern)
    )

    total = (await db.execute(
        select(func.count())
        .select_from(IngestionJob)
        .join(Source, IngestionJob.source_id == Source.id)
        .where(where_clause),
    )).scalar_one()

    rows = (await db.execute(
        select(
            IngestionJob,
            file_count_sq,
            source_label_expr.label("source_label"),
            Source.type.label("source_type"),
            Source.brand.label("source_brand"),
        )
        .join(Source, IngestionJob.source_id == Source.id)
        .where(where_clause)
        .order_by(IngestionJob.started_at.desc().nulls_last())
        .limit(limit),
    )).all()

    items = [
        {
            "id": job.id,
            "source_id": job.source_id,
            "source_label": label or "",
            "source_type": s_type or "",
            "status": job.status,
            "progress_pct": job.progress_pct,
            "discovered_count": discovered or 0,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "error_message": job.error_message,
            "brand": s_brand,
        }
        for job, discovered, label, s_type, s_brand in rows
    ]
    return {"items": items, "total": total}
