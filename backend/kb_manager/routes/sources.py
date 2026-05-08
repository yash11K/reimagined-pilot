"""Sources API routes — flat reads from denormalized source rows.

List endpoint reads only `sources` (no joins). Detail endpoint adds 3 small
queries: parent lookup, run history, active files. All counters/state are
maintained on the source row by writers + DB triggers.
"""

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.database import get_db
from kb_manager.queries import files as file_queries
from kb_manager.queries import jobs as job_queries
from kb_manager.queries import queue as queue_queries
from kb_manager.queries import sources as source_queries
from kb_manager.schemas.sources import (
    ActiveFileInfo,
    FileStats,
    FilterCounts,
    ReingestRequest,
    ReingestResponse,
    RunHistoryEntry,
    RuntimeInfo,
    SourceDetail,
    SourceListResponse,
    SourceSummary,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class ConfirmSourceRequest(BaseModel):
    action: str  # "process" | "discard"
    reviewed_by: str | None = None


# ---------------------------------------------------------------------------
# GET /sources
# ---------------------------------------------------------------------------

@router.get("/sources", response_model=SourceListResponse)
async def list_sources(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    type: str | None = None,
    status: str | None = None,
    region: str | None = None,
    brand: str | None = None,
    kb_target: str | None = None,
    search: str | None = Query(None, description="ILIKE on URL + nav_label"),
    origin: str | None = Query(None, description="'manual' or 'discovered'"),
    include_counts: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> SourceListResponse:
    """Flat list — single SELECT against `sources`, no joins."""
    result = await source_queries.list_sources(
        db, page=page, size=size, type=type, status=status,
        region=region, brand=brand, kb_target=kb_target, search=search,
        origin=origin,
    )

    items = [
        SourceSummary(
            id=s.id,
            url=s.url,
            type=s.type,
            origin=s.origin,
            region=s.region,
            brand=s.brand,
            kb_target=s.kb_target,
            status=s.status,
            display_status=s.display_status,
            run_count=s.run_count,
            last_run_at=s.last_run_at,
            created_at=s.created_at,
        )
        for s in result["items"]
    ]

    counts = None
    if include_counts:
        raw = await source_queries.get_filter_counts(
            db,
            type=type, status=status, region=region, brand=brand,
            kb_target=kb_target, origin=origin, search=search,
        )
        counts = FilterCounts(
            by_status=raw["by_status"],
            by_region=raw["by_region"],
            by_brand=raw["by_brand"],
            by_origin=raw["by_origin"],
        )

    return SourceListResponse(
        items=items,
        total=result["total"],
        page=result["page"],
        size=result["size"],
        pages=result["pages"],
        counts=counts,
    )


# ---------------------------------------------------------------------------
# GET /sources/pending-review (review page — discovered awaiting HITL)
# ---------------------------------------------------------------------------

@router.get("/sources/pending-review", response_model=SourceListResponse)
async def list_sources_pending_review(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> SourceListResponse:
    """Discovered sources awaiting human approval (HITL queue)."""
    result = await source_queries.list_sources_pending_review(db, page=page, size=size)
    items = [
        SourceSummary(
            id=s.id, url=s.url, type=s.type, origin=s.origin,
            region=s.region, brand=s.brand, kb_target=s.kb_target,
            status=s.status, display_status=s.display_status,
            run_count=s.run_count, last_run_at=s.last_run_at,
            created_at=s.created_at,
        )
        for s in result["items"]
    ]
    return SourceListResponse(
        items=items, total=result["total"], page=result["page"],
        size=result["size"], pages=result["pages"],
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

    # 3 small queries — all serial in same session (acceptable for detail page)
    stats = await file_queries.count_files_by_status(db, source_id)
    run_history = await source_queries.get_run_history(db, source_id, limit=50)
    active_files = await file_queries.list_active_files_for_source(db, source_id)

    parent_url = None
    if source.parent_source_id is not None:
        parent = await source_queries.get_source(db, source.parent_source_id)
        if parent is not None:
            parent_url = parent.url

    # Runtime: only when there's an active queue item
    runtime = None
    queue_item = await queue_queries.get_active_queue_item_for_source(db, source_id)
    if queue_item is not None:
        position = await queue_queries.get_queue_position(db, source_id)
        runtime = RuntimeInfo(
            queue_position=position,
            worker_id=queue_item.worker_id,
        )

    steering_prompt = await job_queries.get_latest_steering_prompt(db, source_id)

    return SourceDetail(
        id=source.id,
        url=source.url,
        type=source.type,
        origin=source.origin,
        region=source.region,
        brand=source.brand,
        kb_target=source.kb_target,
        status=source.status,
        display_status=source.display_status,
        run_count=source.run_count,
        last_run_at=source.last_run_at,
        metadata=source.metadata_,
        scout_summary=source.scout_summary,
        created_at=source.created_at,
        parent_url=parent_url,
        file_stats=FileStats(
            total=stats["total"],
            approved=stats["approved"],
            pending=stats["pending_review"],
            rejected=stats["rejected"],
        ),
        active_files=[
            ActiveFileInfo(id=f.id, title=f.title, status=f.status)
            for f in active_files
        ],
        run_history=[RunHistoryEntry(**r) for r in run_history],
        runtime=runtime,
        steering_prompt=steering_prompt,
    )


# ---------------------------------------------------------------------------
# POST /sources/{source_id}/confirm — HITL approval for discovered sources
# ---------------------------------------------------------------------------

@router.post("/sources/{source_id}/confirm", status_code=202)
async def confirm_source(
    source_id: uuid.UUID,
    body: ConfirmSourceRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
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
        job = await job_queries.create_job(
            db, source_id=source_id, status="scouting",
        )
        await source_queries.update_source(
            db, source_id,
            status="active",
            display_status="queued",
            active_job_id=job.id,
        )
        await queue_queries.add_to_queue(
            db, source_id=source_id, job_id=job.id,
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
    """Delete source. CASCADE clears jobs/files/queue rows; S3 cleanup runs async."""
    source = await source_queries.get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")

    # Capture S3 keys before cascade — query active files (rare >1 case OK).
    files = await file_queries.list_active_files_for_source(db, source_id)
    s3_keys = [f.s3_key for f in files if f.s3_key]

    await source_queries.delete_source(db, source_id)
    await db.commit()

    if s3_keys:
        background_tasks.add_task(
            _cleanup_s3_keys, s3_keys, request.app.state.s3_uploader,
        )


async def _cleanup_s3_keys(s3_keys: list[str], s3_uploader) -> None:
    for key in s3_keys:
        try:
            await s3_uploader.delete(key)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# POST /sources/{source_id}/reingest
# ---------------------------------------------------------------------------

@router.post("/sources/{source_id}/reingest", status_code=202, response_model=ReingestResponse)
async def reingest_source(
    source_id: uuid.UUID,
    body: ReingestRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ReingestResponse:
    """Trigger re-ingestion: create a new job + enqueue against this source."""
    source = await source_queries.get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")

    if source.status == "needs_confirmation":
        raise HTTPException(
            status_code=409,
            detail="Source must be confirmed before re-ingestion",
        )

    if source.active_job_id is not None:
        raise HTTPException(
            status_code=409,
            detail="A run is already in progress for this source",
        )

    steering = body.steering_prompt
    if steering is None:
        steering = await job_queries.get_latest_steering_prompt(db, source_id)

    job = await job_queries.create_job(
        db, source_id=source_id, status="scouting",
        steering_prompt=steering,
    )
    await source_queries.update_source(
        db, source_id,
        active_job_id=job.id,
        display_status="queued",
    )
    await queue_queries.add_to_queue(
        db, source_id=source_id,
        priority=body.priority or 0,
        job_id=job.id,
    )
    await db.commit()

    worker = getattr(request.app.state, "queue_worker", None)
    if worker is not None:
        worker.notify()

    return ReingestResponse(job_id=job.id, source_id=source_id, status="scouting")
