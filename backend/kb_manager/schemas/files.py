"""Request/response schemas for the files API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SourceRef(BaseModel):
    """Lightweight source reference in file responses."""

    id: UUID
    url: str


class FileSummary(BaseModel):
    """Summary representation of a KB file for list views."""

    id: UUID
    title: str
    status: str
    region: str | None
    brand: str | None
    kb_target: str
    category: str | None = None
    visibility: str | None = None
    tags: list[str] | None = None
    quality_verdict: str | None
    uniqueness_verdict: str | None
    source_url: str | None
    created_at: datetime


class SimilarFile(BaseModel):
    """Hydrated reference to a similar KB file."""

    id: UUID
    title: str
    source_url: str | None


class FileDetail(FileSummary):
    """Full file detail including content, QA results, and review metadata."""

    md_content: str
    modify_date: datetime | None
    quality_reasoning: str | None
    uniqueness_reasoning: str | None
    similar_files: list[SimilarFile]
    s3_key: str | None
    reviewed_by: str | None
    review_notes: str | None
    job_id: UUID
    sources: list[SourceRef]


class ApproveRequest(BaseModel):
    """Request body for POST /files/{file_id}/approve."""

    reviewed_by: str
    notes: str | None = None


class RejectRequest(BaseModel):
    """Request body for POST /files/{file_id}/reject."""

    reviewed_by: str
    notes: str


class EditRequest(BaseModel):
    """Request body for PUT /files/{file_id}."""

    md_content: str
    reviewed_by: str


class FileMetadataEdit(BaseModel):
    """Partial metadata + folder move for an existing KB file (PATCH /files/{id}).

    Any field set in the request is applied; unset fields are left unchanged.
    Pass ``folder_id: null`` explicitly to remove the file from its current
    folder (move to the unfiled / "Web Sources" bucket).
    """

    folder_id: UUID | None = None
    title: str | None = None
    brand: str | None = None
    region: str | None = None
    language: str | None = None
    category: str | None = None
    visibility: str | None = None
    tags: list[str] | None = None
    reviewed_by: str | None = None


class CopyRequest(BaseModel):
    """Request body for POST /files/{file_id}/copy."""

    folder_id: UUID


class UploadResponse(BaseModel):
    """Returned from POST /files/upload immediately after the KBFile row is
    created. Enrichment + QA + Uniqueness run in the background — clients
    poll GET /files/{id} for the final status."""

    file_id: UUID
    source_id: UUID
    job_id: UUID
    folder_id: UUID
    status: str          # initial status, always 'pending_review'
    title: str
    deduped: bool        # True when the upload reused an existing Source row
