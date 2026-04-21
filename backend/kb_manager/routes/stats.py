"""Dashboard statistics route — GET /stats."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.database import get_db
from kb_manager.models import IngestionJob, KBFile, Source

router = APIRouter()
logger = logging.getLogger(__name__)

# Statuses considered "active" for jobs
_ACTIVE_JOB_STATUSES = ("scouting", "awaiting_confirmation", "processing")


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return aggregate dashboard statistics.

    All counts are computed directly from kb_files, ingestion_jobs, and
    sources tables — no denormalized counters.
    """
    logger.info("📊 GET /stats — computing dashboard statistics")
    # --- kb_files counts ---
    total_files = (
        await db.execute(select(func.count()).select_from(KBFile))
    ).scalar_one()

    pending_review = (
        await db.execute(
            select(func.count()).select_from(KBFile).where(KBFile.status == "pending_review")
        )
    ).scalar_one()

    approved = (
        await db.execute(
            select(func.count()).select_from(KBFile).where(KBFile.status == "approved")
        )
    ).scalar_one()

    rejected = (
        await db.execute(
            select(func.count()).select_from(KBFile).where(KBFile.status == "rejected")
        )
    ).scalar_one()

    kb_public_files = (
        await db.execute(
            select(func.count()).select_from(KBFile).where(KBFile.kb_target == "public")
        )
    ).scalar_one()

    kb_internal_files = (
        await db.execute(
            select(func.count()).select_from(KBFile).where(KBFile.kb_target == "internal")
        )
    ).scalar_one()

    # --- ingestion_jobs counts ---
    active_jobs = (
        await db.execute(
            select(func.count())
            .select_from(IngestionJob)
            .where(IngestionJob.status.in_(_ACTIVE_JOB_STATUSES))
        )
    ).scalar_one()

    failed_jobs_count = (
        await db.execute(
            select(func.count())
            .select_from(IngestionJob)
            .where(IngestionJob.status == "failed")
        )
    ).scalar_one()

    # --- discovered_today: sources created in the last rolling 24h (UTC) ---
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    discovered_today = (
        await db.execute(
            select(func.count())
            .select_from(Source)
            .where(Source.created_at >= cutoff)
        )
    ).scalar_one()

    # --- sources count ---
    sources_count = (
        await db.execute(select(func.count()).select_from(Source))
    ).scalar_one()

    logger.info("📊 Stats: files=%d (pending=%d, approved=%d, rejected=%d), "
                "active_jobs=%d, failed_jobs=%d, discovered_today=%d, sources=%d, "
                "public=%d, internal=%d",
                total_files, pending_review, approved, rejected,
                active_jobs, failed_jobs_count, discovered_today,
                sources_count, kb_public_files, kb_internal_files)

    return {
        "total_files": total_files,
        "pending_review": pending_review,
        "approved": approved,
        "rejected": rejected,
        "active_jobs": active_jobs,
        "failed_jobs_count": failed_jobs_count,
        "discovered_today": discovered_today,
        "sources_count": sources_count,
        "kb_public_files": kb_public_files,
        "kb_internal_files": kb_internal_files,
    }
