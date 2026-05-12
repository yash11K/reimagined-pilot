"""Request/response schemas for the folders API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class FolderCreate(BaseModel):
    """Create a folder. `kb_target` required only when `parent_folder_id` is None
    (root); for subfolders it's inherited from the parent and must be omitted
    or match."""

    name: str = Field(min_length=1, max_length=255)
    parent_folder_id: UUID | None = None
    kb_target: str | None = None
    default_brand: str | None = None
    default_region: str | None = None
    default_language: str | None = None


class FolderUpdate(BaseModel):
    """Rename / update defaults. kb_target and parent are immutable in v1."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    default_brand: str | None = None
    default_region: str | None = None
    default_language: str | None = None


class FolderSummary(BaseModel):
    """List-view representation of a folder."""

    id: UUID
    name: str
    parent_folder_id: UUID | None
    kb_target: str
    default_brand: str | None
    default_region: str | None
    default_language: str | None
    created_at: datetime | None
    updated_at: datetime | None


class BreadcrumbEntry(BaseModel):
    id: UUID
    name: str


class FolderDetail(FolderSummary):
    """Folder detail with breadcrumb chain from root."""

    breadcrumb: list[BreadcrumbEntry]


class FolderListResponse(BaseModel):
    items: list[FolderSummary]
    total: int


class FolderChildFile(BaseModel):
    """File entry shown inside a folder's contents listing."""

    id: UUID
    title: str
    status: str
    brand: str | None
    region: str | None
    category: str | None
    visibility: str | None
    tags: list[str] | None
    quality_verdict: str | None
    uniqueness_verdict: str | None
    s3_key: str | None
    created_at: datetime | None


class FolderContents(BaseModel):
    """Children folders + paginated files in a folder."""

    folder: FolderDetail | None  # None when listing root contents for a kb_target
    child_folders: list[FolderSummary]
    files: list[FolderChildFile]
    files_total: int
    files_page: int
    files_size: int
    files_pages: int
