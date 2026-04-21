"""Files API routes — list, detail, approve, reject, edit, revalidate."""

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kb_manager.database import get_db
from kb_manager.queries import files as file_queries
from kb_manager.models import source_kb_files
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
from kb_manager.services.s3_uploader import S3Uploader

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

async def _upload_to_s3(
    file_id: uuid.UUID,
    s3_uploader: S3Uploader,
    session_factory: async_sessionmaker,
) -> None:
    """Upload an approved file to S3 and update its s3_key."""
    try:
        async with session_factory() as db:
            kb_file = await file_queries.get_file(db, file_id)
            if kb_file is None:
                return

            s3_key = s3_uploader.upload(kb_file)
            if s3_key:
                await file_queries.update_file(db, file_id, s3_key=s3_key)
                await db.commit()
    except Exception:
        logger.exception("💥 S3 upload failed for file %s", file_id)


async def _run_qa_background(
    file_id: uuid.UUID,
    session_factory: async_sessionmaker,
) -> None:
    """Re-run QA on a file and update verdicts via the routing matrix."""
    try:
        from kb_manager.agents.qa import QAAgent
        from kb_manager.services.routing_matrix import route_file

        async with session_factory() as db:
            kb_file = await file_queries.get_file(db, file_id)
            if kb_file is None:
                return

            qa_agent = QAAgent()
            qa_metadata = {
                "title": kb_file.title,
                "source_url": kb_file.source_url,
                "region": kb_file.region,
                "brand": kb_file.brand,
            }
            qa_result = await qa_agent.run(kb_file.md_content, metadata=qa_metadata)

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
    from kb_manager.agents.qa import QAAgent
    from kb_manager.services.routing_matrix import route_file

    kb_file = await file_queries.get_file(db, file_id)
    if kb_file is None:
        return

    qa_agent = QAAgent()
    qa_metadata = {
        "title": kb_file.title,
        "source_url": kb_file.source_url,
        "region": kb_file.region,
        "brand": kb_file.brand,
    }
    qa_result = await qa_agent.run(kb_file.md_content, metadata=qa_metadata)

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
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[FileSummary]:
    result = await file_queries.list_files(
        db, page=page, size=size, status=status,
        region=region, brand=brand, kb_target=kb_target,
        job_id=job_id, source_id=source_id, search=search,
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
    try:
        s3_uploader.delete(s3_key)
    except Exception:
        logger.exception("💥 S3 delete failed for key %s", s3_key)
    try:
        s3_uploader.delete(s3_key + ".metadata.json")
    except Exception:
        pass


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
