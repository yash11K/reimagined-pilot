"""Tests for folder route validation logic (M1).

Mocks `folder_queries` and invokes the route handlers directly — same style
as the other route-layer tests in this suite. We only validate the
HTTP-facing behaviour (status codes, kb_target inheritance, dedupe, empty
checks); query module is exercised separately by an integration suite.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from kb_manager.routes.folders import (
    _cascade_delete_s3,
    create_folder,
    delete_folder,
    get_folder_contents,
    update_folder,
)
from kb_manager.schemas.folders import FolderCreate, FolderUpdate


def _make_folder(
    *,
    id: uuid.UUID | None = None,
    name: str = "root",
    parent_folder_id: uuid.UUID | None = None,
    kb_target: str = "public",
    default_brand: str | None = None,
    default_region: str | None = None,
    default_language: str | None = None,
) -> MagicMock:
    folder = MagicMock()
    folder.id = id or uuid.uuid4()
    folder.name = name
    folder.parent_folder_id = parent_folder_id
    folder.kb_target = kb_target
    folder.default_brand = default_brand
    folder.default_region = default_region
    folder.default_language = default_language
    folder.created_at = None
    folder.updated_at = None
    return folder


# ---------------------------------------------------------------------------
# POST /folders
# ---------------------------------------------------------------------------

class TestCreateFolder:
    @pytest.mark.asyncio
    async def test_root_requires_kb_target(self):
        body = FolderCreate(name="docs")  # no kb_target, no parent
        db = AsyncMock()
        with pytest.raises(HTTPException) as exc:
            await create_folder(body, db)
        assert exc.value.status_code == 422
        assert "kb_target is required" in exc.value.detail

    @pytest.mark.asyncio
    async def test_root_create_happy_path(self):
        body = FolderCreate(name="docs", kb_target="public")
        new_folder = _make_folder(name="docs", kb_target="public")
        db = AsyncMock()

        with patch("kb_manager.routes.folders.folder_queries") as mock_fq:
            mock_fq.name_exists_under_parent = AsyncMock(return_value=False)
            mock_fq.create_folder = AsyncMock(return_value=new_folder)
            mock_fq.get_breadcrumb = AsyncMock(return_value=[new_folder])

            result = await create_folder(body, db)

        assert result.name == "docs"
        assert result.kb_target == "public"
        assert [b.name for b in result.breadcrumb] == ["docs"]
        mock_fq.create_folder.assert_awaited_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_subfolder_inherits_kb_target(self):
        parent = _make_folder(name="root", kb_target="internal")
        body = FolderCreate(name="child", parent_folder_id=parent.id)
        new_folder = _make_folder(
            name="child", parent_folder_id=parent.id, kb_target="internal",
        )
        db = AsyncMock()

        with patch("kb_manager.routes.folders.folder_queries") as mock_fq:
            mock_fq.get_folder = AsyncMock(return_value=parent)
            mock_fq.name_exists_under_parent = AsyncMock(return_value=False)
            mock_fq.create_folder = AsyncMock(return_value=new_folder)
            mock_fq.get_breadcrumb = AsyncMock(return_value=[parent, new_folder])

            result = await create_folder(body, db)

        assert result.kb_target == "internal"
        # kb_target passed into create_folder must be the parent's, not the body's.
        kwargs = mock_fq.create_folder.await_args.kwargs
        assert kwargs["kb_target"] == "internal"
        assert kwargs["parent_folder_id"] == parent.id

    @pytest.mark.asyncio
    async def test_subfolder_rejects_kb_target_mismatch(self):
        parent = _make_folder(name="root", kb_target="internal")
        body = FolderCreate(
            name="child", parent_folder_id=parent.id, kb_target="public",
        )
        db = AsyncMock()

        with patch("kb_manager.routes.folders.folder_queries") as mock_fq:
            mock_fq.get_folder = AsyncMock(return_value=parent)
            with pytest.raises(HTTPException) as exc:
                await create_folder(body, db)

        assert exc.value.status_code == 422
        assert "kb_target must match parent" in exc.value.detail

    @pytest.mark.asyncio
    async def test_subfolder_404_when_parent_missing(self):
        body = FolderCreate(name="child", parent_folder_id=uuid.uuid4())
        db = AsyncMock()
        with patch("kb_manager.routes.folders.folder_queries") as mock_fq:
            mock_fq.get_folder = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc:
                await create_folder(body, db)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_duplicate_name_conflict(self):
        body = FolderCreate(name="docs", kb_target="public")
        db = AsyncMock()
        with patch("kb_manager.routes.folders.folder_queries") as mock_fq:
            mock_fq.name_exists_under_parent = AsyncMock(return_value=True)
            with pytest.raises(HTTPException) as exc:
                await create_folder(body, db)
        assert exc.value.status_code == 409
        assert "already exists" in exc.value.detail


# ---------------------------------------------------------------------------
# PATCH /folders/{id}
# ---------------------------------------------------------------------------

class TestUpdateFolder:
    @pytest.mark.asyncio
    async def test_rename_happy_path(self):
        folder = _make_folder(name="old", kb_target="public")
        renamed = _make_folder(
            id=folder.id, name="new", kb_target="public",
        )
        db = AsyncMock()

        with patch("kb_manager.routes.folders.folder_queries") as mock_fq:
            mock_fq.get_folder = AsyncMock(side_effect=[folder, folder])
            mock_fq.name_exists_under_parent = AsyncMock(return_value=False)
            mock_fq.update_folder = AsyncMock(return_value=renamed)
            mock_fq.get_breadcrumb = AsyncMock(return_value=[renamed])

            result = await update_folder(
                folder.id, FolderUpdate(name="new"), db,
            )

        assert result.name == "new"
        update_kwargs = mock_fq.update_folder.await_args.kwargs
        assert update_kwargs == {"name": "new"}
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rename_conflict(self):
        folder = _make_folder(name="old", kb_target="public")
        db = AsyncMock()
        with patch("kb_manager.routes.folders.folder_queries") as mock_fq:
            mock_fq.get_folder = AsyncMock(return_value=folder)
            mock_fq.name_exists_under_parent = AsyncMock(return_value=True)
            with pytest.raises(HTTPException) as exc:
                await update_folder(
                    folder.id, FolderUpdate(name="taken"), db,
                )
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_noop_when_nothing_provided(self):
        folder = _make_folder(name="root", kb_target="public")
        db = AsyncMock()
        with patch("kb_manager.routes.folders.folder_queries") as mock_fq:
            mock_fq.get_folder = AsyncMock(return_value=folder)
            mock_fq.get_breadcrumb = AsyncMock(return_value=[folder])
            mock_fq.update_folder = AsyncMock()

            result = await update_folder(folder.id, FolderUpdate(), db)

        assert result.name == "root"
        mock_fq.update_folder.assert_not_awaited()
        db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# DELETE /folders/{id}
# ---------------------------------------------------------------------------

def _delete_request() -> MagicMock:
    """FastAPI Request mock with app.state services for cascade."""
    request = MagicMock()
    request.app.state.s3_uploader = MagicMock()
    request.app.state.bedrock_kb_client = MagicMock()
    return request


def _delete_bg() -> MagicMock:
    bg = MagicMock()
    bg.add_task = MagicMock()
    return bg


class TestDeleteFolder:
    @pytest.mark.asyncio
    async def test_delete_empty_succeeds(self):
        folder = _make_folder(kb_target="public")
        db = AsyncMock()
        with patch("kb_manager.routes.folders.folder_queries") as mock_fq:
            mock_fq.get_folder = AsyncMock(return_value=folder)
            mock_fq.is_empty = AsyncMock(return_value=True)
            mock_fq.delete_folder = AsyncMock(return_value=True)

            response = await delete_folder(
                folder.id, _delete_request(), _delete_bg(), False, db,
            )

        assert response.status_code == 204
        mock_fq.delete_folder.assert_awaited_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_non_empty_blocked(self):
        folder = _make_folder(kb_target="public")
        db = AsyncMock()
        with patch("kb_manager.routes.folders.folder_queries") as mock_fq:
            mock_fq.get_folder = AsyncMock(return_value=folder)
            mock_fq.is_empty = AsyncMock(return_value=False)
            with pytest.raises(HTTPException) as exc:
                await delete_folder(
                    folder.id, _delete_request(), _delete_bg(), False, db,
                )
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_cascade_walks_subtree_and_schedules_s3_cleanup(self):
        folder = _make_folder(kb_target="public")
        request = _delete_request()
        bg = _delete_bg()
        db = AsyncMock()
        subtree = [uuid.uuid4(), uuid.uuid4(), folder.id]  # deepest first
        s3_keys = ["public/avis/a.md", "public/avis/b.md"]

        with patch("kb_manager.routes.folders.folder_queries") as mock_fq:
            mock_fq.get_folder = AsyncMock(return_value=folder)
            mock_fq.is_empty = AsyncMock(return_value=False)
            mock_fq.walk_subtree = AsyncMock(return_value=subtree)
            mock_fq.collect_s3_keys_in_folders = AsyncMock(return_value=s3_keys)
            mock_fq.delete_files_in_folders = AsyncMock(return_value=2)
            mock_fq.delete_folder = AsyncMock(return_value=True)

            response = await delete_folder(folder.id, request, bg, True, db)

        assert response.status_code == 204
        # Folders deleted in subtree order (children before parents)
        assert [c.args[1] for c in mock_fq.delete_folder.await_args_list] == subtree
        mock_fq.delete_files_in_folders.assert_awaited_once_with(db, subtree)
        # Exactly one background task scheduled — single batched KB sync
        assert bg.add_task.call_count == 1
        assert bg.add_task.call_args.args[1] == s3_keys

    @pytest.mark.asyncio
    async def test_cascade_no_s3_keys_skips_background_task(self):
        folder = _make_folder(kb_target="public")
        request = _delete_request()
        bg = _delete_bg()
        db = AsyncMock()

        with patch("kb_manager.routes.folders.folder_queries") as mock_fq:
            mock_fq.get_folder = AsyncMock(return_value=folder)
            mock_fq.is_empty = AsyncMock(return_value=False)
            mock_fq.walk_subtree = AsyncMock(return_value=[folder.id])
            mock_fq.collect_s3_keys_in_folders = AsyncMock(return_value=[])
            mock_fq.delete_files_in_folders = AsyncMock(return_value=0)
            mock_fq.delete_folder = AsyncMock(return_value=True)

            response = await delete_folder(folder.id, request, bg, True, db)
        assert response.status_code == 204
        bg.add_task.assert_not_called()


class TestCascadeDeleteS3:
    @pytest.mark.asyncio
    async def test_deletes_each_key_then_triggers_single_sync(self):
        s3 = MagicMock()
        s3.delete = AsyncMock()
        kb = MagicMock()
        kb.start_sync = AsyncMock(return_value="ing-1")
        keys = ["a/b/c.md", "d/e/f.md", "g/h/i.md"]

        await _cascade_delete_s3(keys, s3, kb)

        # Each key deleted (sidecar cascade is inside S3Uploader.delete)
        assert s3.delete.await_count == len(keys)
        # Exactly one sync trigger regardless of key count
        kb.start_sync.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_keys_skips_sync(self):
        s3 = MagicMock()
        s3.delete = AsyncMock()
        kb = MagicMock()
        kb.start_sync = AsyncMock()

        await _cascade_delete_s3([], s3, kb)

        s3.delete.assert_not_called()
        kb.start_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_individual_delete_failure_does_not_abort_others(self):
        s3 = MagicMock()
        s3.delete = AsyncMock(side_effect=[Exception("boom"), None, None])
        kb = MagicMock()
        kb.start_sync = AsyncMock()
        keys = ["a.md", "b.md", "c.md"]

        await _cascade_delete_s3(keys, s3, kb)

        assert s3.delete.await_count == 3
        kb.start_sync.assert_awaited_once()


# ---------------------------------------------------------------------------
# GET /folders/{id}/contents
# ---------------------------------------------------------------------------

class TestFolderContents:
    @pytest.mark.asyncio
    async def test_contents_returns_children_and_files(self):
        folder = _make_folder(name="root", kb_target="public")
        child = _make_folder(name="sub", parent_folder_id=folder.id, kb_target="public")
        kb_file = MagicMock(
            id=uuid.uuid4(), title="a.md", status="pending_review",
            brand=None, region=None, category=None, visibility=None,
            tags=None, quality_verdict=None, uniqueness_verdict=None,
            s3_key=None, created_at=None,
        )
        db = AsyncMock()

        with patch("kb_manager.routes.folders.folder_queries") as mock_fq:
            mock_fq.get_folder = AsyncMock(return_value=folder)
            mock_fq.list_folders = AsyncMock(return_value=[child])
            mock_fq.list_files_in_folder = AsyncMock(return_value={
                "items": [kb_file], "total": 1, "page": 1, "size": 50, "pages": 1,
            })
            mock_fq.get_breadcrumb = AsyncMock(return_value=[folder])

            result = await get_folder_contents(folder.id, 1, 50, db)

        assert len(result.child_folders) == 1
        assert result.child_folders[0].name == "sub"
        assert len(result.files) == 1
        assert result.files[0].title == "a.md"
        assert result.files_total == 1
