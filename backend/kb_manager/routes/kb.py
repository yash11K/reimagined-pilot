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

# Shared client — initialised lazily on first request
_kb_client: BedrockKBClient | None = None


def _get_client() -> BedrockKBClient:
    global _kb_client
    if _kb_client is None:
        _kb_client = BedrockKBClient()
    return _kb_client


# ---------------------------------------------------------------------------
# SSE generators
# ---------------------------------------------------------------------------


async def _search_sse_generator(request: SearchRequest) -> AsyncGenerator[str, None]:
    """Stream Bedrock Retrieve results as SSE events.

    Events emitted:
        result  — one per retrieved chunk (rank, title, snippet, source_url, score, s3_uri)
        error   — if the Bedrock call fails
        search_complete — final event with total_results count
    """
    client = _get_client()
    try:
        results = client.retrieve(
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


async def _chat_sse_generator(request: ChatRequest) -> AsyncGenerator[str, None]:
    """Stream RAG response as SSE events.

    Events emitted:
        sources        — retrieved citations used as context
        token          — generated answer text (single chunk; Bedrock R&G is non-streaming)
        error          — if the Bedrock call fails
        chat_complete  — final event
    """
    client = _get_client()
    try:
        rag = client.retrieve_and_generate(
            query=request.query,
            kb_target=request.kb_target,
            context_limit=request.context_limit,
        )
    except Exception as exc:
        error_data = json.dumps({"error": str(exc)})
        yield f"event: error\ndata: {error_data}\n\n"
        return

    # Emit sources
    sources_data = json.dumps({"sources": rag["citations"]})
    yield f"event: sources\ndata: {sources_data}\n\n"

    # Emit the generated answer — chunked into ~200-char pieces for
    # a streaming feel on the client side.
    text = rag["output_text"]
    chunk_size = 200
    for i in range(0, len(text), chunk_size):
        chunk = text[i : i + chunk_size]
        yield f"event: token\ndata: {json.dumps({'text': chunk})}\n\n"

    yield f"event: chat_complete\ndata: {json.dumps({})}\n\n"


# ---------------------------------------------------------------------------
# POST /kb/search — SSE
# ---------------------------------------------------------------------------


@router.post("/kb/search")
async def kb_search(request: SearchRequest) -> StreamingResponse:
    """Stream search results from the Bedrock Knowledge Base via SSE."""
    logger.info(
        "🔍 POST /kb/search — query='%s', kb_target=%s, limit=%d",
        request.query, request.kb_target, request.limit,
    )
    return StreamingResponse(
        _search_sse_generator(request),
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
async def kb_chat(request: ChatRequest) -> StreamingResponse:
    """RAG chat — retrieve context from Bedrock KB then stream generated answer."""
    logger.info("💬 POST /kb/chat — query='%s', kb_target=%s", request.query, request.kb_target)
    return StreamingResponse(
        _chat_sse_generator(request),
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
    url = s3_uploader.generate_presigned_url(request.s3_uri)
    return {"download_url": url}


# ---------------------------------------------------------------------------
# POST /kb/sync — trigger Bedrock KB data-source ingestion
# ---------------------------------------------------------------------------


@router.post("/kb/sync", response_model=SyncResponse)
async def kb_sync() -> SyncResponse:
    """Trigger a Bedrock Knowledge Base data-source sync.

    Kicks off a StartIngestionJob so Bedrock re-indexes the S3 data source.
    """
    logger.info("🔄 POST /kb/sync — triggering manual KB sync")
    client = _get_client()
    ingestion_id = client.start_sync()
    if ingestion_id is None:
        raise HTTPException(
            status_code=503,
            detail="KB sync unavailable — BEDROCK_DS_ID not configured or sync failed.",
        )
    return SyncResponse(ingestion_job_id=ingestion_id, status="STARTING")
