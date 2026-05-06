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
    sources tables — no denormalized counters. Uses ``COUNT(*) FILTER``
    so each table is scanned at most once per request.
    """
    logger.info("📊 GET /stats — computing dashboard statistics")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    # --- Single pass over kb_files ---
    files_row = (
        await db.execute(
            select(
                func.count().label("total"),
                func.count().filter(KBFile.status == "pending_review").label("pending"),
                func.count().filter(KBFile.status == "approved").label("approved"),
                func.count().filter(KBFile.status == "rejected").label("rejected"),
                func.count().filter(KBFile.kb_target == "public").label("public_files"),
                func.count().filter(KBFile.kb_target == "internal").label("internal_files"),
            ).select_from(KBFile)
        )
    ).one()

    # --- Single pass over ingestion_jobs ---
    jobs_row = (
        await db.execute(
            select(
                func.count().filter(IngestionJob.status.in_(_ACTIVE_JOB_STATUSES)).label("active"),
                func.count().filter(IngestionJob.status == "failed").label("failed"),
            ).select_from(IngestionJob)
        )
    ).one()

    # --- Single pass over sources ---
    sources_row = (
        await db.execute(
            select(
                func.count().label("total"),
                func.count().filter(Source.created_at >= cutoff).label("discovered_today"),
            ).select_from(Source)
        )
    ).one()

    total_files = files_row.total
    pending_review = files_row.pending
    approved = files_row.approved
    rejected = files_row.rejected
    kb_public_files = files_row.public_files
    kb_internal_files = files_row.internal_files
    active_jobs = jobs_row.active
    failed_jobs_count = jobs_row.failed
    sources_count = sources_row.total
    discovered_today = sources_row.discovered_today

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
