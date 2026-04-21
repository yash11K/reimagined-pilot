"""Request/response schemas for the global search API."""

from pydantic import BaseModel

from kb_manager.schemas.files import FileSummary
from kb_manager.schemas.jobs import JobSummary
from kb_manager.schemas.sources import SourceSummary


class FileSearchBucket(BaseModel):
    """File results bucket."""
    items: list[FileSummary]
    total: int


class SourceSearchBucket(BaseModel):
    """Source results bucket."""
    items: list[SourceSummary]
    total: int


class JobSearchBucket(BaseModel):
    """Job results bucket."""
    items: list[JobSummary]
    total: int


class GlobalSearchResponse(BaseModel):
    """Categorised results from a global search."""
    q: str
    files: FileSearchBucket
    sources: SourceSearchBucket
    jobs: JobSearchBucket
