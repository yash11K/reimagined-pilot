"""Pydantic request/response schemas for the KB Manager API."""

from kb_manager.schemas.common import PaginatedResponse
from kb_manager.schemas.files import (
    ApproveRequest,
    EditRequest,
    FileDetail,
    FileSummary,
    RejectRequest,
    SimilarFile,
    SourceRef,
)
from kb_manager.schemas.ingest import (
    AemUrlInput,
    IngestRequest,
    IngestResponse,
    JobCreated,
)
from kb_manager.schemas.kb import ChatRequest, DownloadRequest, SearchRequest
from kb_manager.schemas.sources import (
    FileStats,
    SourceDetail,
    SourceSummary,
)

__all__ = [
    "PaginatedResponse",
    "AemUrlInput",
    "IngestRequest",
    "IngestResponse",
    "JobCreated",
    "FileSummary",
    "SimilarFile",
    "SourceRef",
    "FileDetail",
    "ApproveRequest",
    "RejectRequest",
    "EditRequest",
    "FileStats",
    "SourceSummary",
    "SourceDetail",
    "SearchRequest",
    "ChatRequest",
    "DownloadRequest",
]
