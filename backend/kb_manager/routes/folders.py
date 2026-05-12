"""Folders API routes — CRUD + contents listing + cascade delete."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
)
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.database import get_db
from kb_manager.queries import folders as folder_queries
from kb_manager.schemas.folders import (
    BreadcrumbEntry,
    FolderChildFile,
    FolderContents,
    FolderCreate,
    FolderDetail,
    FolderListResponse,
    FolderSummary,
    FolderUpdate,
)

if TYPE_CHECKING:
    from kb_manager.services.bedrock_kb import BedrockKBClient
    from kb_manager.services.s3_uploader import S3Uploader

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

async def _cascade_delete_s3(
    s3_keys: list[str],
    s3_uploader: "S3Uploader",
    kb_client: "BedrockKBClient | None" = None,
) -> None:
    """Delete each S3 key (+sidecar) then trigger a SINGLE Bedrock KB sync.

    Batching the sync call is important — issuing N syncs for a cascade
    that drops N files would hammer the KB ingestion API and produce
    duplicate ingestion jobs. ``S3Uploader.delete`` already cascades to the
    ``.metadata.json`` sidecar so a single call per key is sufficient.
    """
    for key in s3_keys:
        try:
            await s3_uploader.delete(key)
        except Exception:
            logger.exception("💥 Cascade S3 delete failed for key %s", key)
    if s3_keys and kb_client is not None:
        try:
            ingestion_id = await kb_client.start_sync()
            if ingestion_id:
                logger.info(
                    "🔄 KB sync triggered after folder cascade — ingestionJobId=%s",
                    ingestion_id,
                )
        except Exception:
            logger.warning(
                "⚠️ KB sync trigger failed after cascade delete — non-fatal",
                exc_info=True,
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _folder_to_summary(folder) -> FolderSummary:
    return FolderSummary(
        id=folder.id,
        name=folder.name,
        parent_folder_id=folder.parent_folder_id,
        kb_target=folder.kb_target,
        default_brand=folder.default_brand,
        default_region=folder.default_region,
        default_language=folder.default_language,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )


async def _build_detail(db: AsyncSession, folder) -> FolderDetail:
    chain = await folder_queries.get_breadcrumb(db, folder.id)
    return FolderDetail(
        **_folder_to_summary(folder).model_dump(),
        breadcrumb=[BreadcrumbEntry(id=f.id, name=f.name) for f in chain],
    )


# ---------------------------------------------------------------------------
# POST /folders
# ---------------------------------------------------------------------------

@router.post("/folders", response_model=FolderDetail, status_code=201)
async def create_folder(
    body: FolderCreate,
    db: AsyncSession = Depends(get_db),
) -> FolderDetail:
    if body.parent_folder_id is None:
        # Root: kb_target required.
        if not body.kb_target:
            raise HTTPException(
                status_code=422,
                detail="kb_target is required when creating a root folder",
            )
        kb_target = body.kb_target
    else:
        parent = await folder_queries.get_folder(db, body.parent_folder_id)
        if parent is None:
            raise HTTPException(
                status_code=404,
                detail=f"Parent folder {body.parent_folder_id} not found",
            )
        if body.kb_target is not None and body.kb_target != parent.kb_target:
            raise HTTPException(
                status_code=422,
                detail=(
                    "kb_target must match parent's kb_target "
                    f"('{parent.kb_target}'); subfolders inherit and cannot override"
                ),
            )
        kb_target = parent.kb_target

    # Case-insensitive name dedupe (matches DB partial indexes; pre-check so
    # we can return a clean 409 instead of leaking IntegrityError).
    if await folder_queries.name_exists_under_parent(
        db,
        parent_folder_id=body.parent_folder_id,
        kb_target=kb_target,
        name=body.name,
    ):
        raise HTTPException(
            status_code=409,
            detail=f"A folder named '{body.name}' already exists at this location",
        )

    folder = await folder_queries.create_folder(
        db,
        name=body.name,
        parent_folder_id=body.parent_folder_id,
        kb_target=kb_target,
        default_brand=body.default_brand,
        default_region=body.default_region,
        default_language=body.default_language,
    )
    await db.commit()
    return await _build_detail(db, folder)


# ---------------------------------------------------------------------------
# GET /folders
# ---------------------------------------------------------------------------

@router.get("/folders", response_model=FolderListResponse)
async def list_folders(
    parent_folder_id: uuid.UUID | None = Query(None),
    kb_target: str | None = Query(None, description="Filter root folders by kb_target"),
    roots_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> FolderListResponse:
    folders = await folder_queries.list_folders(
        db,
        parent_folder_id=parent_folder_id,
        kb_target=kb_target,
        roots_only=roots_only or (parent_folder_id is None and kb_target is not None),
    )
    return FolderListResponse(
        items=[_folder_to_summary(f) for f in folders],
        total=len(folders),
    )


# ---------------------------------------------------------------------------
# GET /folders/{id}
# ---------------------------------------------------------------------------

@router.get("/folders/{folder_id}", response_model=FolderDetail)
async def get_folder_detail(
    folder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> FolderDetail:
    folder = await folder_queries.get_folder(db, folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail=f"Folder {folder_id} not found")
    return await _build_detail(db, folder)


# ---------------------------------------------------------------------------
# GET /folders/{id}/contents
# ---------------------------------------------------------------------------

@router.get("/folders/{folder_id}/contents", response_model=FolderContents)
async def get_folder_contents(
    folder_id: uuid.UUID,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> FolderContents:
    folder = await folder_queries.get_folder(db, folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail=f"Folder {folder_id} not found")

    child_folders = await folder_queries.list_folders(
        db, parent_folder_id=folder_id,
    )
    files = await folder_queries.list_files_in_folder(
        db, folder_id, page=page, size=size,
    )
    detail = await _build_detail(db, folder)

    return FolderContents(
        folder=detail,
        child_folders=[_folder_to_summary(f) for f in child_folders],
        files=[
            FolderChildFile(
                id=f.id, title=f.title, status=f.status,
                brand=f.brand, region=f.region,
                category=f.category, visibility=f.visibility, tags=f.tags,
                quality_verdict=f.quality_verdict,
                uniqueness_verdict=f.uniqueness_verdict,
                s3_key=f.s3_key,
                created_at=f.created_at,
            )
            for f in files["items"]
        ],
        files_total=files["total"],
        files_page=files["page"],
        files_size=files["size"],
        files_pages=files["pages"],
    )


# ---------------------------------------------------------------------------
# PATCH /folders/{id}
# ---------------------------------------------------------------------------

@router.patch("/folders/{folder_id}", response_model=FolderDetail)
async def update_folder(
    folder_id: uuid.UUID,
    body: FolderUpdate,
    db: AsyncSession = Depends(get_db),
) -> FolderDetail:
    folder = await folder_queries.get_folder(db, folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail=f"Folder {folder_id} not found")

    updates: dict = {}
    if body.name is not None and body.name != folder.name:
        if await folder_queries.name_exists_under_parent(
            db,
            parent_folder_id=folder.parent_folder_id,
            kb_target=folder.kb_target,
            name=body.name,
            exclude_id=folder.id,
        ):
            raise HTTPException(
                status_code=409,
                detail=f"A folder named '{body.name}' already exists at this location",
            )
        updates["name"] = body.name
    for field in ("default_brand", "default_region", "default_language"):
        value = getattr(body, field)
        if value is not None:
            updates[field] = value

    if not updates:
        return await _build_detail(db, folder)

    updated = await folder_queries.update_folder(db, folder_id, **updates)
    await db.commit()
    return await _build_detail(db, updated)


# ---------------------------------------------------------------------------
# DELETE /folders/{id}
# ---------------------------------------------------------------------------

@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    cascade: bool = Query(
        False,
        description="Delete the folder and all descendants (folders + files + S3 objects)",
    ),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete an empty folder, or cascade-delete a subtree.

    Non-cascade: returns 409 if the folder has any children or files.
    Cascade: walks the subtree deepest-first, bulk-deletes KBFiles inside
    those folders (cascading the source_kb_files junction), then deletes
    each folder row. S3 objects + sidecars are removed in a background
    task that finishes with a single Bedrock KB sync.
    """
    folder = await folder_queries.get_folder(db, folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail=f"Folder {folder_id} not found")

    is_empty = await folder_queries.is_empty(db, folder_id)
    if is_empty:
        await folder_queries.delete_folder(db, folder_id)
        await db.commit()
        return Response(status_code=204)

    if not cascade:
        raise HTTPException(
            status_code=409,
            detail="Folder is not empty. Pass ?cascade=true to delete contents.",
        )

    # Cascade: collect IDs deepest-first so the parent_folder_id RESTRICT
    # constraint is satisfied when we delete folder rows.
    subtree_ids = await folder_queries.walk_subtree(db, folder_id)
    s3_keys = await folder_queries.collect_s3_keys_in_folders(db, subtree_ids)

    deleted_files = await folder_queries.delete_files_in_folders(db, subtree_ids)
    for fid in subtree_ids:
        await folder_queries.delete_folder(db, fid)
    await db.commit()

    logger.info(
        "🗑️ Cascade delete: folder=%s, subtree_size=%d, files_deleted=%d, s3_keys=%d",
        str(folder_id)[:8], len(subtree_ids), deleted_files, len(s3_keys),
    )

    if s3_keys:
        background_tasks.add_task(
            _cascade_delete_s3,
            s3_keys,
            request.app.state.s3_uploader,
            request.app.state.bedrock_kb_client,
        )
    return Response(status_code=204)
