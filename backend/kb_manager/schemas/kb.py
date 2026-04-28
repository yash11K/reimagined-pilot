"""Request/response schemas for the knowledge base search, chat, and sync API."""

from pydantic import BaseModel


class SearchRequest(BaseModel):
    """Request body for POST /kb/search."""

    query: str
    kb_target: str
    limit: int = 10


class ChatRequest(BaseModel):
    """Request body for POST /kb/chat."""

    query: str
    kb_target: str
    context_limit: int = 5


class DownloadRequest(BaseModel):
    """Request body for POST /kb/download."""

    s3_uri: str


class SyncResponse(BaseModel):
    """Response body for POST /kb/sync."""

    ingestion_job_id: str
    status: str
