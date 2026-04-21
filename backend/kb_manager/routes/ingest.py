"""Ingestion API routes — start ingestion, SSE scout/progress streams, content map."""

import asyncio
import json
import logging
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.database import get_db
from kb_manager.queries import jobs as job_queries
from kb_manager.queries import sources as source_queries
from kb_manager.schemas.ingest import (
    IngestRequest,
    IngestResponse,
    JobCreated,
)

router = APIRouter()
logger = logging.getLogger(__name__)

KEEPALIVE_INTERVAL = 15  # seconds


# ---------------------------------------------------------------------------
# SSE generator
# ---------------------------------------------------------------------------

async def _sse_stream_generator(
    request: Request,
    job_id: uuid.UUID,
    channel: str,
    terminal_event: str,
) -> AsyncGenerator[str, None]:
    stream_manager = request.app.state.stream_manager
    job_id_str = str(job_id)
    queue: asyncio.Queue = asyncio.Queue()
    key = (job_id_str, channel)
    stream_manager._channels[key].append(queue)

    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_INTERVAL)
            except asyncio.TimeoutError:
                yield ":keepalive\n\n"
                continue

            if item is None:
                break

            event_type = item.get("event", "message")
            event_data = json.dumps(item.get("data", {}))
            yield f"event: {event_type}\ndata: {event_data}\n\n"

            if event_type == terminal_event:
                break

    except asyncio.CancelledError:
        logger.info("📡 SSE cancelled: job=%s channel=%s", job_id_str[:8], channel)
    finally:
        subscribers = stream_manager._channels.get(key)
        if subscribers is not None:
            try:
                subscribers.remove(queue)
            except ValueError:
                pass


# ---------------------------------------------------------------------------
# Background task wrappers
# ---------------------------------------------------------------------------

async def _run_scout(request: Request, job_id: uuid.UUID, source_url: str, steering_prompt: str | None) -> None:
    pipeline = request.app.state.pipeline
    # run_scout auto-calls run_process at the end
    await pipeline.run_scout(job_id, source_url, steering_prompt)


async def _run_upload_process(request: Request, job_id: uuid.UUID, file_contents: list[bytes]) -> None:
    pipeline = request.app.state.pipeline
    await pipeline.run_upload_process(job_id, file_contents)


# ---------------------------------------------------------------------------
# POST /ingest
# ---------------------------------------------------------------------------

@router.post("/ingest", status_code=202, response_model=IngestResponse)
async def start_ingest(
    request: Request,
    ingest_request: IngestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    """Start ingestion. Creates source + job per URL, triggers auto scout → process."""
    created_jobs: list[JobCreated] = []

    if ingest_request.connector_type == "aem":
        if not ingest_request.urls:
            raise HTTPException(status_code=422, detail="urls required for aem connector")

        for url_input in ingest_request.urls:
            # Normalize: ensure URL ends with .model.json for AEM fetching
            normalized_url = url_input.url
            if not normalized_url.endswith(".model.json"):
                normalized_url = normalized_url.rstrip("/") + ".model.json"

            source = await source_queries.create_source(
                db,
                type="aem",
                url=normalized_url,
                region=url_input.region,
                brand=url_input.brand,
                kb_target=ingest_request.kb_target,
                metadata_={
                    "nav_label": url_input.nav_label,
                    "nav_section": url_input.nav_section,
                    "page_path": url_input.page_path,
                },
            )

            job = await job_queries.create_job(
                db,
                source_id=source.id,
                status="scouting",
                steering_prompt=ingest_request.steering_prompt,
            )

            created_jobs.append(JobCreated(
                job_id=job.id,
                source_id=source.id,
                source_url=normalized_url,
                status="scouting",
            ))

            background_tasks.add_task(
                _run_scout, request, job.id, normalized_url, ingest_request.steering_prompt,
            )

    elif ingest_request.connector_type == "upload":
        source = await source_queries.create_source(
            db,
            type="upload",
            url="upload-batch",
            kb_target=ingest_request.kb_target,
        )
        job = await job_queries.create_job(
            db, source_id=source.id, status="processing",
            steering_prompt=ingest_request.steering_prompt,
        )
        created_jobs.append(JobCreated(
            job_id=job.id, source_id=source.id,
            source_url="upload-batch", status="processing",
        ))
        background_tasks.add_task(_run_upload_process, request, job.id, [])

    await db.commit()
    return IngestResponse(jobs=created_jobs)


# ---------------------------------------------------------------------------
# GET /ingest/{job_id}/scout-stream
# ---------------------------------------------------------------------------

@router.get("/ingest/{job_id}/scout-stream")
async def scout_stream(
    job_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    job = await job_queries.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return StreamingResponse(
        _sse_stream_generator(request, job_id, "scout", "scout_complete"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# GET /ingest/{job_id}/content-map
# ---------------------------------------------------------------------------

@router.get("/ingest/{job_id}/content-map")
async def get_content_map(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return scout summary after scouting completes."""
    job = await job_queries.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if job.status == "scouting":
        raise HTTPException(status_code=409, detail="Scouting still in progress")

    source = job.source
    scout_summary = source.scout_summary or {"components": [], "expansion_source_ids": [], "summary": {}}

    return {
        "job_id": str(job_id),
        "status": job.status,
        "source_url": source.url,
        "source_id": str(source.id),
        "content_map": scout_summary,
    }


# ---------------------------------------------------------------------------
# GET /ingest/{job_id}/progress-stream
# ---------------------------------------------------------------------------

@router.get("/ingest/{job_id}/progress-stream")
async def progress_stream(
    job_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    job = await job_queries.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return StreamingResponse(
        _sse_stream_generator(request, job_id, "progress", "job_complete"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
