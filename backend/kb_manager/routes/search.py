"""Global search route — single query across files, sources, and jobs."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.database import get_db
from kb_manager.queries import search as search_queries
from kb_manager.schemas.files import FileSummary
from kb_manager.schemas.jobs import JobSummary
from kb_manager.schemas.search import (
    FileSearchBucket,
    GlobalSearchResponse,
    JobSearchBucket,
)

router = APIRouter()
logger = logging.getLogger(__name__)

VALID_ENTITIES = {"files", "jobs"}


@router.get("/search", response_model=GlobalSearchResponse)
async def global_search(
    q: str = Query(..., min_length=1, description="Search term"),
    limit: int = Query(5, ge=1, le=50, description="Max results per category"),
    entity: str | None = Query(
        None,
        description="Comma-separated entity filter: files,jobs. Omit for all.",
    ),
    db: AsyncSession = Depends(get_db),
) -> GlobalSearchResponse:
    """Search across file titles/tags and job labels."""

    # Determine which buckets to query
    if entity is not None:
        requested = {e.strip() for e in entity.split(",") if e.strip()}
        invalid = requested - VALID_ENTITIES
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid entity filter(s): {', '.join(sorted(invalid))}. "
                       f"Valid values: {', '.join(sorted(VALID_ENTITIES))}",
            )
    else:
        requested = VALID_ENTITIES

    empty_file_bucket = FileSearchBucket(items=[], total=0)
    empty_job_bucket = JobSearchBucket(items=[], total=0)

    # Fan out queries
    if "files" in requested:
        raw_files = await search_queries.search_files(db, q, limit=limit)
        file_bucket = FileSearchBucket(
            items=[FileSummary(**f) for f in raw_files["items"]],
            total=raw_files["total"],
        )
    else:
        file_bucket = empty_file_bucket

    if "jobs" in requested:
        raw_jobs = await search_queries.search_jobs(db, q, limit=limit)
        job_bucket = JobSearchBucket(
            items=[JobSummary(**j) for j in raw_jobs["items"]],
            total=raw_jobs["total"],
        )
    else:
        job_bucket = empty_job_bucket

    return GlobalSearchResponse(
        q=q,
        files=file_bucket,
        jobs=job_bucket,
    )
