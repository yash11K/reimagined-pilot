"""Sources API routes — list, detail, active jobs, confirm, delete."""

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kb_manager.database import get_db
from kb_manager.models import KBFile
from kb_manager.queries import files as file_queries
from kb_manager.queries import jobs as job_queries
from kb_manager.queries import queue as queue_queries
from kb_manager.queries import sources as source_queries
from kb_manager.schemas.common import PaginatedResponse
from kb_manager.schemas.sources import (
    FileStats,
    SourceDetail,
    SourceSummary,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class ConfirmSourceRequest(BaseModel):
    action: str  # "process" | "discard"
    reviewed_by: str | None = None


# ---------------------------------------------------------------------------
# Background helpers
# ---------------------------------------------------------------------------

async def _delete_source_files_from_s3(
    source_id: uuid.UUID,
    session_factory: async_sessionmaker,
    s3_uploader,
) -> None:
    """Delete all S3 objects for files linked to a source."""
    try:
        async with session_factory() as db:
            stats = await file_queries.count_files_by_status(db, source_id)
            # Fetch all files for this source
            result = await file_queries.list_files(db, source_id=source_id, size=1000)
            for f in result["items"]:
                if f.s3_key:
                    # ``S3Uploader.delete`` cascades to the metadata sidecar.
                    await s3_uploader.delete(f.s3_key)
                await file_queries.delete_file(db, f.id)
            await db.commit()
    except Exception:
        logger.exception("💥 S3 cleanup failed for source %s", source_id)


# ---------------------------------------------------------------------------
# GET /sources/active-jobs
# ---------------------------------------------------------------------------

@router.get("/sources/active-jobs")
async def get_active_jobs(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Map source_id → job_id for all active jobs."""
    active_jobs = await job_queries.get_active_jobs(db)
    mapping = {str(job.source_id): str(job.id) for job in active_jobs}
    return {"active_jobs": mapping}


# ---------------------------------------------------------------------------
# GET /sources
# ---------------------------------------------------------------------------

@router.get("/sources", response_model=PaginatedResponse[SourceSummary])
async def list_sources(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    type: str | None = None,
    status: str | None = None,
    region: str | None = None,
    brand: str | None = None,
    kb_target: str | None = None,
    search: str | None = Query(None, description="ILIKE match on URL"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[SourceSummary]:
    result = await source_queries.list_sources(
        db, page=page, size=size, type=type, status=status,
        region=region, brand=brand, kb_target=kb_target, search=search,
    )
    items: list[SourceSummary] = []
    for s in result["items"]:
        job_count = await source_queries.get_source_job_count(db, s.id)
        items.append(SourceSummary(
            id=s.id,
            url=s.url,
            type=s.type,
            region=s.region,
            brand=s.brand,
            kb_target=s.kb_target,
            status=s.status,
            is_scouted=s.is_scouted,
            is_ingested=s.is_ingested,
            created_at=s.created_at,
            job_count=job_count,
        ))
    return PaginatedResponse[SourceSummary](
        items=items,
        total=result["total"],
        page=result["page"],
        size=result["size"],
        pages=result["pages"],
    )


# ---------------------------------------------------------------------------
# GET /sources/{source_id}
# ---------------------------------------------------------------------------

@router.get("/sources/{source_id}", response_model=SourceDetail)
async def get_source_detail(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> SourceDetail:
    source = await source_queries.get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")

    stats = await file_queries.count_files_by_status(db, source_id)

    return SourceDetail(
        id=source.id,
        url=source.url,
        type=source.type,
        region=source.region,
        brand=source.brand,
        kb_target=source.kb_target,
        status=source.status,
        is_scouted=source.is_scouted,
        is_ingested=source.is_ingested,
        metadata=source.metadata_,
        scout_summary=source.scout_summary,
        last_ingested_at=source.last_ingested_at,
        created_at=source.created_at,
        file_stats=FileStats(
            total=stats["total"],
            approved=stats["approved"],
            pending=stats["pending_review"],
            rejected=stats["rejected"],
        ),
    )


# ---------------------------------------------------------------------------
# POST /sources/{source_id}/confirm
# ---------------------------------------------------------------------------

@router.post("/sources/{source_id}/confirm", status_code=202)
async def confirm_source(
    source_id: uuid.UUID,
    body: ConfirmSourceRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Confirm or discard a source in needs_confirmation state.

    process → start a new independent ingestion job for this source.
    discard → mark dismissed, no extraction.
    """
    source = await source_queries.get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")

    if source.status != "needs_confirmation":
        raise HTTPException(status_code=409, detail="Source not in needs_confirmation state")

    if body.action == "discard":
        await source_queries.dismiss_source(db, source_id)
        await db.commit()
        return {"source_id": str(source_id), "status": "dismissed"}

    if body.action == "process":
        await source_queries.update_source(db, source_id, status="active")
        # Create the job inline so the response carries the id, then enqueue
        # the URL bound to that job. Worker handles graceful shutdown + retry.
        job = await job_queries.create_job(
            db, source_id=source_id, status="scouting",
        )
        await queue_queries.add_to_queue(
            db,
            url=source.url,
            region=source.region,
            brand=source.brand,
            kb_target=source.kb_target,
            job_id=job.id,
        )
        await db.commit()

        worker = getattr(request.app.state, "queue_worker", None)
        if worker is not None:
            worker.notify()

        return {"source_id": str(source_id), "job_id": str(job.id), "status": "scouting"}

    raise HTTPException(status_code=422, detail="action must be 'process' or 'discard'")


# ---------------------------------------------------------------------------
# DELETE /sources/{source_id}
# ---------------------------------------------------------------------------

@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(
    source_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a source. ``ON DELETE CASCADE`` on ``ingestion_jobs.source_id``
    and ``kb_files.job_id`` (plus the existing junction CASCADE) clears all
    child rows; S3 cleanup runs in the background.
    """
    source = await source_queries.get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")

    # Capture S3 keys before the cascade deletes the kb_files rows.
    files_result = await file_queries.list_files(db, source_id=source_id, size=1000)
    s3_keys = [f.s3_key for f in files_result["items"] if f.s3_key]

    await source_queries.delete_source(db, source_id)
    await db.commit()

    if s3_keys:
        background_tasks.add_task(
            _cleanup_s3_keys, s3_keys, request.app.state.s3_uploader,
        )


async def _cleanup_s3_keys(s3_keys: list[str], s3_uploader) -> None:
    # ``S3Uploader.delete`` cascades to the metadata sidecar, so one call per key.
    for key in s3_keys:
        try:
            await s3_uploader.delete(key)
        except Exception:
            pass
