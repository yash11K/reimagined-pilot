"""Files API routes — list, detail, approve, reject, edit, revalidate."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kb_manager.database import get_db
from kb_manager.queries import files as file_queries
from kb_manager.queries import folders as folder_queries
from kb_manager.queries import jobs as job_queries
from kb_manager.queries import sources as source_queries
from kb_manager.models import source_kb_files
from kb_manager.schemas.common import PaginatedResponse
from kb_manager.schemas.files import (
    ApproveRequest,
    CopyRequest,
    EditRequest,
    FileDetail,
    FileMetadataEdit,
    FileSummary,
    RejectRequest,
    SimilarFile,
    SourceRef,
    UploadResponse,
)
from kb_manager.services.s3_uploader import S3Uploader
from kb_manager.services.upload_context import resolve_upload_context

if TYPE_CHECKING:
    from kb_manager.services.bedrock_kb import BedrockKBClient
    from kb_manager.services.pipeline import Pipeline

router = APIRouter()
logger = logging.getLogger(__name__)

# Upload constraints — markdown / text only on day one (per the file-manager
# v1 scope). Size cap defends against accidental huge pastes; raise once the
# Bedrock ingestion path is proven for large docs.
_UPLOAD_MAX_BYTES = 10 * 1024 * 1024
_UPLOAD_ALLOWED_EXTS = (".md", ".markdown", ".txt")


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

async def _upload_to_s3(
    file_id: uuid.UUID,
    s3_uploader: S3Uploader,
    session_factory: async_sessionmaker,
    kb_client: "BedrockKBClient | None" = None,
) -> None:
    """Upload an approved file to S3 and update its s3_key, then trigger KB sync."""
    try:
        async with session_factory() as db:
            kb_file = await file_queries.get_file(db, file_id)
            if kb_file is None:
                return

            namespace, folder_path = await resolve_upload_context(db, kb_file)
            s3_key = await s3_uploader.upload(
                kb_file, namespace=namespace, folder_path=folder_path,
            )
            if s3_key:
                await file_queries.update_file(db, file_id, s3_key=s3_key)
                await db.commit()

                # Trigger Bedrock KB sync after successful upload
                if kb_client is not None:
                    try:
                        ingestion_id = await kb_client.start_sync()
                        if ingestion_id:
                            logger.info("🔄 KB sync triggered after approve upload — ingestionJobId=%s", ingestion_id)
                    except Exception:
                        logger.warning("⚠️ KB sync trigger failed after approve upload — non-fatal", exc_info=True)
    except Exception:
        logger.exception("💥 S3 upload failed for file %s", file_id)


async def _recompute_after_edit(
    file_id: uuid.UUID,
    old_s3_key: str | None,
    s3_uploader: S3Uploader,
    session_factory: async_sessionmaker,
    kb_client: "BedrockKBClient | None" = None,
) -> None:
    """Re-upload the file under a fresh S3 key after a key-segment edit.

    A key-segment edit is any change to ``title``, ``brand``, ``region``, or
    ``language`` — fields that participate in the S3 key path. The old key
    is deleted only if the new upload succeeds (see
    ``S3Uploader.recompute_s3_location``).
    """
    try:
        async with session_factory() as db:
            kb_file = await file_queries.get_file(db, file_id)
            if kb_file is None:
                return
            namespace, folder_path = await resolve_upload_context(db, kb_file)
            new_key = await s3_uploader.recompute_s3_location(
                kb_file, old_s3_key,
                namespace=namespace, folder_path=folder_path,
            )
            if new_key and new_key != old_s3_key:
                await file_queries.update_file(db, file_id, s3_key=new_key)
                await db.commit()
        if kb_client is not None:
            try:
                ingestion_id = await kb_client.start_sync()
                if ingestion_id:
                    logger.info(
                        "🔄 KB sync triggered after metadata recompute — ingestionJobId=%s",
                        ingestion_id,
                    )
            except Exception:
                logger.warning(
                    "⚠️ KB sync trigger failed after recompute — non-fatal",
                    exc_info=True,
                )
    except Exception:
        logger.exception("💥 Recompute S3 failed for file %s", file_id)


async def _resync_sidecar_only(
    file_id: uuid.UUID,
    s3_uploader: S3Uploader,
    session_factory: async_sessionmaker,
    kb_client: "BedrockKBClient | None" = None,
) -> None:
    """Re-upload only the metadata sidecar after a cosmetic metadata edit.

    Cheap — one put_object. The content file is untouched. Triggers a KB
    sync so Bedrock picks up the new sidecar attributes (e.g. updated
    category / tags / folder_path).
    """
    try:
        async with session_factory() as db:
            kb_file = await file_queries.get_file(db, file_id)
            if kb_file is None or kb_file.s3_key is None:
                return
            _, folder_path = await resolve_upload_context(db, kb_file)
            await s3_uploader.resync_metadata(kb_file, folder_path=folder_path)
        if kb_client is not None:
            try:
                ingestion_id = await kb_client.start_sync()
                if ingestion_id:
                    logger.info(
                        "🔄 KB sync triggered after sidecar resync — ingestionJobId=%s",
                        ingestion_id,
                    )
            except Exception:
                logger.warning(
                    "⚠️ KB sync trigger failed after sidecar resync — non-fatal",
                    exc_info=True,
                )
    except Exception:
        logger.exception("💥 Sidecar resync failed for file %s", file_id)


async def _run_upload_pipeline(
    file_id: uuid.UUID,
    pipeline: "Pipeline",
    folder_defaults: dict[str, str] | None,
) -> None:
    """Wrap ``Pipeline.process_upload`` for use as a FastAPI BackgroundTask.

    The pipeline already handles its own error path (mark rejected on
    failure); this shim exists so the route can stay agnostic about how
    pipeline is wired into app state.
    """
    try:
        await pipeline.process_upload(file_id, folder_defaults=folder_defaults)
    except Exception:
        # process_upload already logs and rejects internally — this catch
        # only exists to keep the BackgroundTask wrapper from leaking.
        logger.exception("💥 Upload pipeline shim failed for file %s", file_id)


async def _run_qa_background(
    file_id: uuid.UUID,
    session_factory: async_sessionmaker,
) -> None:
    """Re-run QA + Uniqueness on a file and update verdicts via the routing matrix."""
    try:
        from kb_manager.agents.qa import run_qa_and_uniqueness
        from kb_manager.services.routing_matrix import route_file

        async with session_factory() as db:
            kb_file = await file_queries.get_file(db, file_id)
            if kb_file is None:
                return

            qa_metadata = {
                "title": kb_file.title,
                "source_url": kb_file.source_url,
                "region": kb_file.region,
                "brand": kb_file.brand,
            }
            qa_result = await run_qa_and_uniqueness(kb_file.md_content, metadata=qa_metadata)

            metadata_complete = all([
                kb_file.title,
                kb_file.source_url,
                kb_file.region,
                kb_file.brand,
            ])

            status = route_file(
                qa_result.quality_verdict,
                qa_result.uniqueness_verdict,
                metadata_complete,
            )

            await file_queries.update_file(
                db, file_id,
                quality_verdict=qa_result.quality_verdict,
                quality_reasoning=qa_result.quality_reasoning,
                uniqueness_verdict=qa_result.uniqueness_verdict,
                uniqueness_reasoning=qa_result.uniqueness_reasoning,
                similar_file_ids=[
                    uuid.UUID(sid) for sid in qa_result.similar_file_ids if sid
                ] or None,
                status=status,
            )
            await db.commit()
    except Exception:
        logger.exception("💥 QA re-run failed for file %s", file_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _hydrate_similar_files(
    db: AsyncSession, similar_file_ids: list[uuid.UUID] | None,
) -> list[SimilarFile]:
    if not similar_file_ids:
        return []
    result: list[SimilarFile] = []
    for fid in similar_file_ids:
        sf = await file_queries.get_file(db, fid)
        if sf is not None:
            result.append(SimilarFile(id=sf.id, title=sf.title, source_url=sf.source_url))
    return result


def _get_source_refs(file) -> list[SourceRef]:
    """Build SourceRef list from the M2M relationship."""
    refs: list[SourceRef] = []
    if hasattr(file, "sources") and file.sources:
        for src in file.sources:
            refs.append(SourceRef(id=src.id, url=src.url))
    return refs


def _file_to_detail(file, similar_files: list[SimilarFile], source_refs: list[SourceRef]) -> FileDetail:
    return FileDetail(
        id=file.id,
        title=file.title,
        status=file.status,
        region=file.region,
        brand=file.brand,
        kb_target=file.kb_target,
        category=file.category,
        visibility=file.visibility,
        tags=file.tags,
        quality_verdict=file.quality_verdict,
        uniqueness_verdict=file.uniqueness_verdict,
        source_url=file.source_url,
        created_at=file.created_at,
        md_content=file.md_content,
        modify_date=file.modify_date,
        quality_reasoning=file.quality_reasoning,
        uniqueness_reasoning=file.uniqueness_reasoning,
        similar_files=similar_files,
        s3_key=file.s3_key,
        reviewed_by=file.reviewed_by,
        review_notes=file.review_notes,
        job_id=file.job_id,
        sources=source_refs,
    )


async def _run_qa_sync(file_id: uuid.UUID, db: AsyncSession) -> None:
    from kb_manager.agents.qa import run_qa_and_uniqueness
    from kb_manager.services.routing_matrix import route_file

    kb_file = await file_queries.get_file(db, file_id)
    if kb_file is None:
        return

    qa_metadata = {
        "title": kb_file.title,
        "source_url": kb_file.source_url,
        "region": kb_file.region,
        "brand": kb_file.brand,
    }
    qa_result = await run_qa_and_uniqueness(kb_file.md_content, metadata=qa_metadata)

    metadata_complete = all([
        kb_file.title,
        kb_file.source_url,
        kb_file.region,
        kb_file.brand,
    ])

    status = route_file(
        qa_result.quality_verdict,
        qa_result.uniqueness_verdict,
        metadata_complete,
    )

    await file_queries.update_file(
        db, file_id,
        quality_verdict=qa_result.quality_verdict,
        quality_reasoning=qa_result.quality_reasoning,
        uniqueness_verdict=qa_result.uniqueness_verdict,
        uniqueness_reasoning=qa_result.uniqueness_reasoning,
        similar_file_ids=[
            uuid.UUID(sid) for sid in qa_result.similar_file_ids if sid
        ] or None,
        status=status,
    )


# ---------------------------------------------------------------------------
# POST /files/upload
# ---------------------------------------------------------------------------

def _folder_defaults(folder) -> dict[str, str]:
    """Return non-null folder-level metadata defaults as a flat dict.

    Used as a prior over MetadataEnricher output — folder values win.
    """
    out: dict[str, str] = {}
    if folder.default_brand:
        out["brand"] = folder.default_brand
    if folder.default_region:
        out["region"] = folder.default_region
    if folder.default_language:
        out["language"] = folder.default_language
    return out


def _validate_upload(file: UploadFile, body: bytes) -> None:
    """Reject uploads that violate size/extension/encoding rules."""
    if not file.filename:
        raise HTTPException(status_code=422, detail="file must have a filename")
    name_lower = file.filename.lower()
    if not name_lower.endswith(_UPLOAD_ALLOWED_EXTS):
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type. Allowed: {', '.join(_UPLOAD_ALLOWED_EXTS)}"
            ),
        )
    if len(body) == 0:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")
    if len(body) > _UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {_UPLOAD_MAX_BYTES // (1024 * 1024)} MB limit",
        )


def _decode_markdown(body: bytes, filename: str) -> str:
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"File '{filename}' is not valid UTF-8 text: {exc}",
        )


@router.post("/files/upload", response_model=UploadResponse, status_code=201)
async def upload_file(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    folder_id: uuid.UUID = Form(...),
    title: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    """Upload a markdown / text file directly into a folder.

    Flow:
      1. Validate the file (extension, size, UTF-8).
      2. Get-or-create a content-addressable ``Source`` (``upload://<sha256>``)
         so re-uploading identical bytes dedupes at the source level.
      3. Create a synthetic completed ``IngestionJob`` (KBFile.job_id is
         NOT NULL — making it nullable would ripple across the codebase, so
         we mint a placeholder job per upload instead).
      4. Create the ``KBFile`` row with ``folder_id`` set, inherit kb_target
         and any folder defaults, mark ``pending_review``.
      5. Kick the background enrichment + QA pipeline. The route returns
         immediately with the file_id; clients poll GET /files/{id}.
    """
    folder = await folder_queries.get_folder(db, folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail=f"Folder {folder_id} not found")

    body = await file.read()
    _validate_upload(file, body)
    md_content = _decode_markdown(body, file.filename or "<unnamed>")

    # Content-addressable: identical bytes → identical Source URL → UPSERT
    # collapses repeated uploads into one Source row. We still create a
    # fresh KBFile per upload attempt so retries after a rejection can be
    # tracked independently.
    sha256 = hashlib.sha256(body).hexdigest()
    upload_url = f"upload://{sha256}/{file.filename}"

    initial_title = (title or file.filename or "Untitled").rsplit(".", 1)[0] or "Untitled"

    # Step 2: get-or-create Source. `source_queries.create_source` does the
    # UPSERT against (type, url).
    existing_source = await source_queries.get_source_by_url(
        db, upload_url, type="upload",
    )
    source = await source_queries.create_source(
        db,
        type="upload",
        url=upload_url,
        origin="manual",
        kb_target=folder.kb_target,
        region=folder.default_region,
        brand=folder.default_brand,
        language=folder.default_language,
        metadata_={
            "original_filename": file.filename,
            "uploaded_via": "files_manager",
            "folder_id": str(folder.id),
        },
    )
    deduped = existing_source is not None

    # Step 3: synthetic IngestionJob (status='completed' since there's no
    # async URL fetch to wait on — the bytes are already in hand).
    job = await job_queries.create_job(
        db,
        source_id=source.id,
        status="completed",
        progress_pct=100,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )

    # Step 4: KBFile lands pending_review; enrichment fills metadata next.
    kb_file = await file_queries.create_file(
        db,
        job_id=job.id,
        folder_id=folder.id,
        title=initial_title,
        md_content=md_content,
        source_url=upload_url,
        region=folder.default_region,
        brand=folder.default_brand,
        kb_target=folder.kb_target,
        language=folder.default_language,
        status="pending_review",
    )
    await file_queries.link_source_to_file(db, source.id, kb_file.id)
    await db.commit()

    # Step 5: background enrichment + QA pipeline.
    pipeline = request.app.state.pipeline
    background_tasks.add_task(
        _run_upload_pipeline,
        kb_file.id,
        pipeline,
        _folder_defaults(folder),
    )

    return UploadResponse(
        file_id=kb_file.id,
        source_id=source.id,
        job_id=job.id,
        folder_id=folder.id,
        status=kb_file.status,
        title=kb_file.title,
        deduped=deduped,
    )


# ---------------------------------------------------------------------------
# GET /files
# ---------------------------------------------------------------------------

@router.get("/files", response_model=PaginatedResponse[FileSummary])
async def list_files(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    region: str | None = None,
    brand: str | None = None,
    kb_target: str | None = None,
    job_id: uuid.UUID | None = None,
    source_id: uuid.UUID | None = None,
    folder_id: uuid.UUID | None = Query(
        None, description="Only files inside this folder",
    ),
    unfiled: bool = Query(
        False,
        description=(
            "Only files with no folder (the 'Web Sources' virtual bucket — "
            "covers legacy URL-ingested KBFiles). Ignored when folder_id is set."
        ),
    ),
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[FileSummary]:
    result = await file_queries.list_files(
        db, page=page, size=size, status=status,
        region=region, brand=brand, kb_target=kb_target,
        job_id=job_id, source_id=source_id, search=search,
        folder_id=folder_id, unfiled=unfiled,
    )
    items = [
        FileSummary(
            id=f.id, title=f.title, status=f.status,
            region=f.region, brand=f.brand, kb_target=f.kb_target,
            category=f.category, visibility=f.visibility, tags=f.tags,
            quality_verdict=f.quality_verdict,
            uniqueness_verdict=f.uniqueness_verdict,
            source_url=f.source_url, created_at=f.created_at,
        )
        for f in result["items"]
    ]
    return PaginatedResponse[FileSummary](
        items=items, total=result["total"],
        page=result["page"], size=result["size"], pages=result["pages"],
    )


# ---------------------------------------------------------------------------
# GET /files/{file_id}
# ---------------------------------------------------------------------------

@router.get("/files/{file_id}", response_model=FileDetail)
async def get_file_detail(
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> FileDetail:
    file = await file_queries.get_file(db, file_id)
    if file is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    similar_files = await _hydrate_similar_files(db, file.similar_file_ids)
    source_refs = _get_source_refs(file)
    return _file_to_detail(file, similar_files, source_refs)


# ---------------------------------------------------------------------------
# POST /files/{file_id}/approve
# ---------------------------------------------------------------------------

@router.post("/files/{file_id}/approve", response_model=FileDetail)
async def approve_file(
    file_id: uuid.UUID,
    request: ApproveRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    db: AsyncSession = Depends(get_db),
) -> FileDetail:
    file = await file_queries.get_file(db, file_id)
    if file is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    updated = await file_queries.update_file(
        db, file_id,
        status="approved",
        reviewed_by=request.reviewed_by,
        review_notes=request.notes,
    )
    await db.commit()

    background_tasks.add_task(
        _upload_to_s3, file_id,
        req.app.state.s3_uploader, req.app.state.session_factory,
        req.app.state.bedrock_kb_client,
    )

    similar_files = await _hydrate_similar_files(db, updated.similar_file_ids)
    source_refs = _get_source_refs(updated)
    return _file_to_detail(updated, similar_files, source_refs)


# ---------------------------------------------------------------------------
# POST /files/{file_id}/reject
# ---------------------------------------------------------------------------

@router.post("/files/{file_id}/reject", response_model=FileDetail)
async def reject_file(
    file_id: uuid.UUID,
    request: RejectRequest,
    db: AsyncSession = Depends(get_db),
) -> FileDetail:
    file = await file_queries.get_file(db, file_id)
    if file is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    updated = await file_queries.update_file(
        db, file_id,
        status="rejected",
        reviewed_by=request.reviewed_by,
        review_notes=request.notes,
    )
    await db.commit()

    similar_files = await _hydrate_similar_files(db, updated.similar_file_ids)
    source_refs = _get_source_refs(updated)
    return _file_to_detail(updated, similar_files, source_refs)


# ---------------------------------------------------------------------------
# PUT /files/{file_id}
# ---------------------------------------------------------------------------

@router.put("/files/{file_id}", response_model=FileDetail)
async def edit_file(
    file_id: uuid.UUID,
    request: EditRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    db: AsyncSession = Depends(get_db),
) -> FileDetail:
    file = await file_queries.get_file(db, file_id)
    if file is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    updated = await file_queries.update_file(
        db, file_id,
        md_content=request.md_content,
        reviewed_by=request.reviewed_by,
    )
    await db.commit()

    background_tasks.add_task(
        _run_qa_background, file_id, req.app.state.session_factory,
    )

    similar_files = await _hydrate_similar_files(db, updated.similar_file_ids)
    source_refs = _get_source_refs(updated)
    return _file_to_detail(updated, similar_files, source_refs)


# ---------------------------------------------------------------------------
# PATCH /files/{file_id} — metadata edit + folder move
# ---------------------------------------------------------------------------

# Fields whose change rewrites the S3 key path; an edit to any of these on an
# already-uploaded file triggers a ``recompute_s3_location`` background task.
# Cosmetic fields (category/visibility/tags) and ``folder_id`` only need a
# sidecar re-upload.
_KEY_SEGMENT_FIELDS = ("title", "brand", "region", "language")
_COSMETIC_FIELDS = ("category", "visibility", "tags")


@router.patch("/files/{file_id}", response_model=FileDetail)
async def edit_file_metadata(
    file_id: uuid.UUID,
    body: FileMetadataEdit,
    background_tasks: BackgroundTasks,
    req: Request,
    db: AsyncSession = Depends(get_db),
) -> FileDetail:
    """Partial metadata edit and/or folder move.

    Only fields explicitly present in the request body are applied — Pydantic's
    ``exclude_unset=True`` is used to distinguish "set null" from "omitted".

    Propagation to S3 + Bedrock depends on which fields changed:

      - Key-segment fields (title/brand/region/language) → background
        ``recompute_s3_location`` (delete old key + upload new).
      - Cosmetic fields (category/visibility/tags) and folder move →
        background sidecar-only re-upload.
      - Files without ``s3_key`` (not yet uploaded) skip S3 work entirely.

    Cross-kb_target moves are forbidden (would require recompute + Bedrock
    rebucket; deferred past v1).
    """
    file = await file_queries.get_file(db, file_id)
    if file is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    updates = body.model_dump(exclude_unset=True)
    # reviewed_by is recorded but doesn't participate in S3 propagation
    # decisions — strip it out of the diff and apply separately.
    has_review = "reviewed_by" in updates
    if has_review and not updates["reviewed_by"]:
        updates.pop("reviewed_by")

    # 1. Validate folder_id change (cross-kb_target forbidden in v1)
    if "folder_id" in updates and updates["folder_id"] != file.folder_id:
        new_folder_id = updates["folder_id"]
        if new_folder_id is not None:
            target = await folder_queries.get_folder(db, new_folder_id)
            if target is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Target folder {new_folder_id} not found",
                )
            if target.kb_target != file.kb_target:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Cross-kb_target move forbidden in v1: file kb_target="
                        f"'{file.kb_target}', target folder kb_target="
                        f"'{target.kb_target}'"
                    ),
                )

    # 2. Classify the change for S3 propagation
    key_segment_changed = any(
        f in updates and updates[f] != getattr(file, f)
        for f in _KEY_SEGMENT_FIELDS
    )
    sidecar_relevant_changed = (
        any(
            f in updates and updates[f] != getattr(file, f)
            for f in _COSMETIC_FIELDS
        )
        or ("folder_id" in updates and updates["folder_id"] != file.folder_id)
    )

    old_s3_key = file.s3_key

    # 3. Apply updates
    if updates:
        await file_queries.update_file(db, file_id, **updates)
    await db.commit()

    # 4. Propagate to S3 only when the file actually has a key
    if old_s3_key:
        if key_segment_changed:
            background_tasks.add_task(
                _recompute_after_edit,
                file_id, old_s3_key,
                req.app.state.s3_uploader,
                req.app.state.session_factory,
                req.app.state.bedrock_kb_client,
            )
        elif sidecar_relevant_changed:
            background_tasks.add_task(
                _resync_sidecar_only,
                file_id,
                req.app.state.s3_uploader,
                req.app.state.session_factory,
                req.app.state.bedrock_kb_client,
            )

    refreshed = await file_queries.get_file(db, file_id)
    similar_files = await _hydrate_similar_files(db, refreshed.similar_file_ids)
    source_refs = _get_source_refs(refreshed)
    return _file_to_detail(refreshed, similar_files, source_refs)


# ---------------------------------------------------------------------------
# POST /files/{file_id}/copy
# ---------------------------------------------------------------------------

@router.post("/files/{file_id}/copy", response_model=FileDetail, status_code=201)
async def copy_file(
    file_id: uuid.UUID,
    body: CopyRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    db: AsyncSession = Depends(get_db),
) -> FileDetail:
    """Physical copy: new KBFile row + S3 object + sidecar in the target folder.

    QA + Uniqueness are NOT re-run on the copy — the verdicts carry over
    from the source row, but ``uniqueness_verdict`` is forced to
    ``overlapping`` and the source's id is pushed into ``similar_file_ids``
    so the audit trail records the lineage.

    Same-kb_target only in v1 (target folder must match source file's
    kb_target).
    """
    src = await file_queries.get_file(db, file_id)
    if src is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    target = await folder_queries.get_folder(db, body.folder_id)
    if target is None:
        raise HTTPException(
            status_code=404, detail=f"Target folder {body.folder_id} not found",
        )
    if target.kb_target != src.kb_target:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Cross-kb_target copy forbidden in v1: source kb_target="
                f"'{src.kb_target}', target folder kb_target='{target.kb_target}'"
            ),
        )

    # Junction lookup — copy inherits the source's source_id linkage so the
    # synthetic IngestionJob has a valid parent. For files without any
    # linked Source (shouldn't happen post-pipeline, but defend) we 409.
    from sqlalchemy import select
    src_links_stmt = select(source_kb_files.c.source_id).where(
        source_kb_files.c.kb_file_id == src.id,
    )
    src_source_ids = [
        row[0] for row in (await db.execute(src_links_stmt)).all()
    ]
    if not src_source_ids:
        raise HTTPException(
            status_code=409,
            detail="Source file has no linked Source; cannot establish copy lineage",
        )

    primary_source_id = src_source_ids[0]

    # Synthetic completed job — KBFile.job_id is NOT NULL, so each KBFile
    # needs an IngestionJob anchor. status='completed' since there's no
    # async fetch to wait on.
    job = await job_queries.create_job(
        db,
        source_id=primary_source_id,
        status="completed",
        progress_pct=100,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )

    new_file = await file_queries.create_file(
        db,
        job_id=job.id,
        folder_id=target.id,
        title=src.title,
        md_content=src.md_content,
        source_url=src.source_url,
        region=src.region,
        brand=src.brand,
        kb_target=src.kb_target,
        language=src.language,
        category=src.category,
        visibility=src.visibility,
        tags=src.tags,
        status=src.status,
        quality_verdict=src.quality_verdict,
        quality_reasoning=src.quality_reasoning,
        # Force overlapping + record lineage. A copy is by definition not
        # unique — running Uniqueness again would just re-discover this.
        uniqueness_verdict="overlapping",
        uniqueness_reasoning=f"Copy of file {src.id}",
        similar_file_ids=[src.id],
        modify_date=src.modify_date,
    )

    # Mirror the source's M2M linkage onto the copy.
    for sid in src_source_ids:
        await file_queries.link_source_to_file(db, sid, new_file.id)

    await db.commit()

    # If the source was already uploaded to S3 (status='approved' AND s3_key
    # set), upload the copy to its own S3 location + trigger KB sync. The
    # copy lives at a different S3 key (different folder namespace) so
    # Bedrock will index it as a distinct chunk.
    if src.status == "approved" and src.s3_key:
        background_tasks.add_task(
            _upload_to_s3,
            new_file.id,
            req.app.state.s3_uploader,
            req.app.state.session_factory,
            req.app.state.bedrock_kb_client,
        )

    similar_files = await _hydrate_similar_files(db, new_file.similar_file_ids)
    source_refs = _get_source_refs(new_file)
    return _file_to_detail(new_file, similar_files, source_refs)


# ---------------------------------------------------------------------------
# POST /files/{file_id}/revalidate
# ---------------------------------------------------------------------------

@router.post("/files/{file_id}/revalidate", response_model=FileDetail)
async def revalidate_file(
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> FileDetail:
    file = await file_queries.get_file(db, file_id)
    if file is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    await _run_qa_sync(file_id, db)

    updated = await file_queries.get_file(db, file_id)
    await db.commit()

    similar_files = await _hydrate_similar_files(db, updated.similar_file_ids)
    source_refs = _get_source_refs(updated)
    return _file_to_detail(updated, similar_files, source_refs)


# ---------------------------------------------------------------------------
# DELETE /files/{file_id}
# ---------------------------------------------------------------------------

async def _delete_s3_file(s3_key: str, s3_uploader) -> None:
    # ``S3Uploader.delete`` already cascades to the metadata sidecar, so a
    # single call is sufficient.
    try:
        await s3_uploader.delete(s3_key)
    except Exception:
        logger.exception("💥 S3 delete failed for key %s", s3_key)


@router.delete("/files/{file_id}", status_code=204)
async def delete_file(
    file_id: uuid.UUID,
    req: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Hard-delete a KB file. Async S3 cleanup in background."""
    file = await file_queries.get_file(db, file_id)
    if file is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    s3_key = file.s3_key
    deleted = await file_queries.delete_file(db, file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")
    await db.commit()

    if s3_key:
        background_tasks.add_task(_delete_s3_file, s3_key, req.app.state.s3_uploader)

    return Response(status_code=204)
