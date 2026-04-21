"""Knowledge Base routes — search, chat, and download."""

import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from kb_manager.schemas.kb import ChatRequest, DownloadRequest, SearchRequest

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Placeholder SSE generators (Bedrock KB integration wired in Phase 7)
# ---------------------------------------------------------------------------


async def _search_sse_generator(request: SearchRequest) -> AsyncGenerator[str, None]:
    """Stub SSE generator for KB search.

    Yields placeholder result events followed by a search_complete event.
    Will be replaced with real Bedrock KB retrieval later.
    """
    # Emit a single stub result
    result_data = json.dumps({
        "rank": 1,
        "title": "Stub result",
        "snippet": f"Placeholder result for query: {request.query}",
        "source_url": "https://example.com/stub",
        "score": 0.0,
    })
    yield f"event: result\ndata: {result_data}\n\n"

    # Emit search_complete
    complete_data = json.dumps({"total_results": 1})
    yield f"event: search_complete\ndata: {complete_data}\n\n"


async def _chat_sse_generator(request: ChatRequest) -> AsyncGenerator[str, None]:
    """Stub SSE generator for KB RAG chat.

    Yields placeholder sources, token, and chat_complete events.
    Will be replaced with real Bedrock KB retrieval + LLM streaming later.
    """
    # Emit sources
    sources_data = json.dumps({
        "sources": [
            {
                "title": "Stub source",
                "url": "https://example.com/stub",
                "snippet": "Placeholder context for chat",
            }
        ]
    })
    yield f"event: sources\ndata: {sources_data}\n\n"

    # Emit a stub token
    token_data = json.dumps({"text": f"Stub answer for: {request.query}"})
    yield f"event: token\ndata: {token_data}\n\n"

    # Emit chat_complete
    complete_data = json.dumps({})
    yield f"event: chat_complete\ndata: {complete_data}\n\n"


# ---------------------------------------------------------------------------
# POST /kb/search — SSE
# ---------------------------------------------------------------------------


@router.post("/kb/search")
async def kb_search(request: SearchRequest) -> StreamingResponse:
    """Stream search results from the knowledge base via SSE."""
    logger.info("🔍 POST /kb/search — query='%s', kb_target=%s", request.query, getattr(request, 'kb_target', None))
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
    """RAG chat — retrieve context then stream generated answer via SSE."""
    logger.info("💬 POST /kb/chat — query='%s'", request.query)
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
async def kb_download(request: DownloadRequest) -> dict:
    """Return a presigned S3 download URL for the given s3_uri.

    Currently returns a stub URL. Will use S3Uploader.generate_presigned_url()
    once it is implemented in Phase 5.
    """
    logger.info("📥 POST /kb/download — s3_uri=%s", request.s3_uri)
    return {
        "download_url": f"https://stub-presigned-url.s3.amazonaws.com/{request.s3_uri}"
    }
