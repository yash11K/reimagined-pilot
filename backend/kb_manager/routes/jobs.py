"""Jobs API routes — list ingestion jobs with computed fields."""

import logging
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.database import get_db
from kb_manager.queries import jobs as job_queries
from kb_manager.schemas.common import PaginatedResponse
from kb_manager.schemas.jobs import JobSummary

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
