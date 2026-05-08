"""Jobs API routes — list ingestion jobs with computed fields."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.database import get_db
from kb_manager.queries import jobs as job_queries
from kb_manager.queries import run_pages as run_page_queries
from kb_manager.schemas.common import PaginatedResponse
from kb_manager.schemas.jobs import JobSummary, RunPageResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/jobs", response_model=PaginatedResponse[JobSummary])
async def list_jobs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="Comma-separated statuses"),
    source_id: uuid.UUID | None = Query(None),
    brand: str | None = Query(None),
    sort: str = Query("started_at:desc", description="field:dir, e.g. started_at:desc"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[JobSummary]:
    """List ingestion jobs with source label, discovered count, and progress."""
    result = await job_queries.list_jobs_extended(
        db,
        page=page,
        size=size,
        status=status,
        source_id=source_id,
        brand=brand,
        sort=sort,
    )

    items = [JobSummary(**item) for item in result["items"]]

    return PaginatedResponse[JobSummary](
        items=items,
        total=result["total"],
        page=result["page"],
        size=result["size"],
        pages=result["pages"],
    )


@router.get("/jobs/{job_id}/pages", response_model=PaginatedResponse[RunPageResponse])
async def list_job_pages(
    job_id: uuid.UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[RunPageResponse]:
    """List paginated RunPage records for a given job."""
    # Verify job exists
    job = await job_queries.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    result = await run_page_queries.list_run_pages(db, job_id=job_id, page=page, size=size)

    items = [
        RunPageResponse(
            id=rp.id,
            job_id=rp.job_id,
            url=rp.url,
            outcome=rp.outcome,
            reason=rp.reason,
            bytes=rp.bytes,
            file_id=rp.file_id,
            created_at=rp.created_at,
        )
        for rp in result["items"]
    ]

    return PaginatedResponse[RunPageResponse](
        items=items,
        total=result["total"],
        page=result["page"],
        size=result["size"],
        pages=result["pages"],
    )
