"""Knowledge Base routes — search, chat, download, and sync."""

import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from kb_manager.schemas.kb import ChatRequest, DownloadRequest, SearchRequest, SyncResponse
from kb_manager.services.bedrock_kb import BedrockKBClient

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SSE generators
# ---------------------------------------------------------------------------


async def _search_sse_generator(
    request: SearchRequest, client: BedrockKBClient,
) -> AsyncGenerator[str, None]:
    """Stream Bedrock Retrieve results as SSE events.

    Events emitted:
        result  — one per retrieved chunk (rank, title, snippet, source_url, score, s3_uri)
        error   — if the Bedrock call fails
        search_complete — final event with total_results count
    """
    try:
        results = await client.retrieve(
            query=request.query,
            kb_target=request.kb_target,
            limit=request.limit,
        )
    except Exception as exc:
        error_data = json.dumps({"error": str(exc)})
        yield f"event: error\ndata: {error_data}\n\n"
        return

    for item in results:
        yield f"event: result\ndata: {json.dumps(item)}\n\n"

    complete_data = json.dumps({"total_results": len(results)})
    yield f"event: search_complete\ndata: {complete_data}\n\n"


async def _chat_sse_generator(
    request: ChatRequest, client: BedrockKBClient,
) -> AsyncGenerator[str, None]:
    """Emit the RAG response as SSE events.

    Bedrock ``retrieve_and_generate`` is **non-streaming** — the call blocks
    until the full answer is ready. We deliberately emit one ``answer``
    event with the complete text instead of fake-chunking 200-char slices,
    so consumers don't mistake this for real token streaming.

    Events emitted:
        sources        — retrieved citations used as context
        answer         — full generated text (single payload)
        error          — if the Bedrock call fails
        chat_complete  — final event
    """
    try:
        rag = await client.retrieve_and_generate(
            query=request.query,
            kb_target=request.kb_target,
            context_limit=request.context_limit,
        )
    except Exception as exc:
        error_data = json.dumps({"error": str(exc)})
        yield f"event: error\ndata: {error_data}\n\n"
        return

    sources_data = json.dumps({"sources": rag["citations"]})
    yield f"event: sources\ndata: {sources_data}\n\n"

    answer_data = json.dumps({"text": rag["output_text"]})
    yield f"event: answer\ndata: {answer_data}\n\n"

    yield f"event: chat_complete\ndata: {json.dumps({})}\n\n"


# ---------------------------------------------------------------------------
# POST /kb/search — SSE
# ---------------------------------------------------------------------------


@router.post("/kb/search")
async def kb_search(request: SearchRequest, req: Request) -> StreamingResponse:
    """Stream search results from the Bedrock Knowledge Base via SSE."""
    logger.info(
        "🔍 POST /kb/search — query='%s', kb_target=%s, limit=%d",
        request.query, request.kb_target, request.limit,
    )
    client: BedrockKBClient = req.app.state.bedrock_kb_client
    return StreamingResponse(
        _search_sse_generator(request, client),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# POST /kb/chat — SSE
# ---------------------------------------------------------------------------


@router.post("/kb/chat")
async def kb_chat(request: ChatRequest, req: Request) -> StreamingResponse:
    """RAG chat — retrieve context from Bedrock KB then stream generated answer."""
    logger.info("💬 POST /kb/chat — query='%s', kb_target=%s", request.query, request.kb_target)
    client: BedrockKBClient = req.app.state.bedrock_kb_client
    return StreamingResponse(
        _chat_sse_generator(request, client),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# POST /kb/download
# ---------------------------------------------------------------------------


@router.post("/kb/download")
async def kb_download(request: DownloadRequest, req: Request) -> dict:
    """Return a presigned S3 download URL for the given s3_uri."""
    logger.info("📥 POST /kb/download — s3_uri=%s", request.s3_uri)
    s3_uploader = req.app.state.s3_uploader
    url = await s3_uploader.generate_presigned_url(request.s3_uri)
    return {"download_url": url}


# ---------------------------------------------------------------------------
# POST /kb/sync — trigger Bedrock KB data-source ingestion
# ---------------------------------------------------------------------------


@router.post("/kb/sync", response_model=SyncResponse)
async def kb_sync(req: Request) -> SyncResponse:
    """Trigger a Bedrock Knowledge Base data-source sync.

    Kicks off a StartIngestionJob so Bedrock re-indexes the S3 data source.
    """
    logger.info("🔄 POST /kb/sync — triggering manual KB sync")
    client: BedrockKBClient = req.app.state.bedrock_kb_client
    ingestion_id = await client.start_sync()
    if ingestion_id is None:
        raise HTTPException(
            status_code=503,
            detail="KB sync unavailable — BEDROCK_DS_ID not configured or sync failed.",
        )
    return SyncResponse(ingestion_job_id=ingestion_id, status="STARTING")
