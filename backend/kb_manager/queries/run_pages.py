"""CRUD and pagination queries for the run_pages table."""

import logging
import math
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.models import RunPage

logger = logging.getLogger(__name__)


async def create_run_page(
    db: AsyncSession,
    *,
    job_id: uuid.UUID,
    url: str,
    outcome: str,
    reason: str | None = None,
    bytes: int | None = None,
    file_id: uuid.UUID | None = None,
) -> RunPage:
    """Create a new RunPage record for a job."""
    run_page = RunPage(
        job_id=job_id,
        url=url,
        outcome=outcome,
        reason=reason,
        bytes=bytes,
        file_id=file_id,
    )
    db.add(run_page)
    await db.flush()
    await db.refresh(run_page)
    logger.info(
        "📄 RunPage created: job=%s, url=%s, outcome=%s",
        str(job_id)[:8],
        url[:80],
        outcome,
    )
    return run_page


async def list_run_pages(
    db: AsyncSession,
    *,
    job_id: uuid.UUID,
    page: int = 1,
    size: int = 20,
) -> dict:
    """List run pages for a job with pagination."""
    query = select(RunPage).where(RunPage.job_id == job_id)
    count_query = select(func.count()).select_from(RunPage).where(RunPage.job_id == job_id)

    total = (await db.execute(count_query)).scalar_one()
    offset = (page - 1) * size
    query = query.offset(offset).limit(size).order_by(RunPage.created_at.asc())

    result = await db.execute(query)
    items = list(result.scalars().all())
    pages = math.ceil(total / size) if size > 0 else 0

    return {"items": items, "total": total, "page": page, "size": size, "pages": pages}
