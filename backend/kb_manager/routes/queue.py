"""Queue API routes — list queue, counts, live event stream.

The queue is keyed by source_id. URLs are no longer accepted directly;
callers should POST /sources or /ingest first to create a Source, then
hit /sources/{id}/reingest to enqueue.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.database import get_db
from kb_manager.queries import queue as queue_queries

router = APIRouter()
logger = logging.getLogger(__name__)


class QueueItemResponse(BaseModel):
    id: str
    source_id: str
    status: str
    job_id: str | None
    error_message: str | None
    retry_count: int
    max_retries: int
    priority: int
    created_at: str | None
    started_at: str | None


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
                source_id=str(i.source_id),
                status=i.status,
                job_id=str(i.job_id) if i.job_id else None,
                error_message=i.error_message,
                retry_count=i.retry_count,
                max_retries=i.max_retries,
                priority=i.priority,
                created_at=i.created_at.isoformat() if i.created_at else None,
                started_at=i.started_at.isoformat() if i.started_at else None,
            )
            for i in items
        ],
        "counts": counts,
        "max_workers": worker.max_workers if worker else 0,
        "active_workers": worker.active_count if worker else 0,
    }


@router.get("/queue/counts")
async def queue_counts(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    counts = await queue_queries.get_queue_counts(db)
    worker = getattr(request.app.state, "queue_worker", None)
    return {
        "counts": counts,
        "max_workers": worker.max_workers if worker else 0,
        "active_workers": worker.active_count if worker else 0,
    }


@router.get("/events/stream")
async def event_stream(request: Request) -> StreamingResponse:
    """SSE stream of typed pipeline events."""
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


@router.get("/logs/stream")
async def log_stream(request: Request) -> StreamingResponse:
    return await event_stream(request)
