"""Queue API routes — add URLs, list queue, live event stream."""

import asyncio
import json
import logging
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.database import get_db
from kb_manager.queries import queue as queue_queries

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class QueueAddRequest(BaseModel):
    urls: list[str]
    region: str | None = None
    brand: str | None = None
    kb_target: str = "public"
    priority: int = 0


class QueueItemResponse(BaseModel):
    id: str
    url: str
    region: str | None
    brand: str | None
    kb_target: str
    status: str
    job_id: str | None
    error_message: str | None
    retry_count: int
    max_retries: int
    priority: int
    created_at: str | None
    started_at: str | None
    completed_at: str | None


# ---------------------------------------------------------------------------
# POST /queue — Add URLs to the worker queue
# ---------------------------------------------------------------------------

@router.post("/queue", status_code=202)
async def add_to_queue(
    request: Request,
    body: QueueAddRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    logger.info("📥 POST /queue — %d URLs, kb_target=%s", len(body.urls), body.kb_target)
    items = []
    skipped = 0
    for url in body.urls:
        item = await queue_queries.add_to_queue(
            db, url=url, region=body.region, brand=body.brand,
            kb_target=body.kb_target, priority=body.priority,
        )
        if item is not None:
            items.append(str(item.id))
        else:
            skipped += 1
    await db.commit()

    # Notify the worker that new items are available
    worker = getattr(request.app.state, "queue_worker", None)
    if worker:
        worker.notify()

    logger.info("✅ %d URLs queued, %d skipped (duplicate)", len(items), skipped)
    return {"queued": len(items), "skipped": skipped, "item_ids": items}


# ---------------------------------------------------------------------------
# GET /queue — List queue items
# ---------------------------------------------------------------------------

@router.get("/queue")
async def list_queue(
    request: Request,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    items = await queue_queries.get_queue_items(db, status=status)
    counts = await queue_queries.get_queue_counts(db)

    worker = getattr(request.app.state, "queue_worker", None)

    return {
        "items": [
            QueueItemResponse(
                id=str(i.id),
                url=i.url,
                region=i.region,
                brand=i.brand,
                kb_target=i.kb_target,
                status=i.status,
                job_id=str(i.job_id) if i.job_id else None,
                error_message=i.error_message,
                retry_count=i.retry_count,
                max_retries=i.max_retries,
                priority=i.priority,
                created_at=i.created_at.isoformat() if i.created_at else None,
                started_at=i.started_at.isoformat() if i.started_at else None,
                completed_at=i.completed_at.isoformat() if i.completed_at else None,
            )
            for i in items
        ],
        "counts": counts,
        "max_workers": worker._max_workers if worker else 0,
        "active_workers": worker.active_count if worker else 0,
    }


# ---------------------------------------------------------------------------
# GET /queue/counts — Lightweight counts + worker info (no item list)
# ---------------------------------------------------------------------------

@router.get("/queue/counts")
async def queue_counts(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    counts = await queue_queries.get_queue_counts(db)
    worker = getattr(request.app.state, "queue_worker", None)
    return {
        "counts": counts,
        "max_workers": worker._max_workers if worker else 0,
        "active_workers": worker.active_count if worker else 0,
    }


# ---------------------------------------------------------------------------
# GET /events/stream — Live typed event stream via SSE
# ---------------------------------------------------------------------------

@router.get("/events/stream")
async def event_stream(request: Request) -> StreamingResponse:
    """SSE stream of typed pipeline events.

    Events have the shape: {"timestamp": ..., "topic": "...", "event": "...", "data": {...}}
    Topics: worker, queue, progress, tokens
    """
    logger.info("📡 Event stream opened")

    async def generate() -> AsyncGenerator[str, None]:
        event_queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        stream_manager = request.app.state.stream_manager

        stream_manager.add_event_subscriber(event_queue)
        try:
            while True:
                try:
                    item = await asyncio.wait_for(event_queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ":keepalive\n\n"
                    continue

                if item is None:
                    break

                yield f"data: {json.dumps(item)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            stream_manager.remove_event_subscriber(event_queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# Keep /logs/stream as alias for backward compatibility
@router.get("/logs/stream")
async def log_stream(request: Request) -> StreamingResponse:
    """Legacy SSE stream — redirects to /events/stream."""
    return await event_stream(request)
