"""Tests for M6: legacy-file surfacing via folder_id / unfiled filters.

Two surfaces covered:
  - ``GET /files`` accepts ``folder_id`` and ``unfiled`` query params and
    passes them through to ``file_queries.list_files``.
  - The PATCH file route allows moving a legacy (folder_id=None) file into
    a folder, exercising the "one-way move into a folder" path described
    in the plan.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from kb_manager.routes.files import (
    _resync_sidecar_only,
    edit_file_metadata,
    list_files,
)
from kb_manager.schemas.files import FileMetadataEdit


# ---------------------------------------------------------------------------
# GET /files filter passthrough
# ---------------------------------------------------------------------------

class TestListFilesFolderFilter:
    @pytest.mark.asyncio
    async def test_folder_id_filter_passed_through(self):
        folder_id = uuid.uuid4()
        db = AsyncMock()
        with patch("kb_manager.routes.files.file_queries") as mock_files:
            mock_files.list_files = AsyncMock(return_value={
                "items": [], "total": 0, "page": 1, "size": 20, "pages": 0,
            })
            await list_files(
                page=1, size=20, status=None, region=None, brand=None,
                kb_target=None, job_id=None, source_id=None,
                folder_id=folder_id, unfiled=False, search=None, db=db,
            )

        kwargs = mock_files.list_files.await_args.kwargs
        assert kwargs["folder_id"] == folder_id
        assert kwargs["unfiled"] is False

    @pytest.mark.asyncio
    async def test_unfiled_filter_passed_through(self):
        db = AsyncMock()
        with patch("kb_manager.routes.files.file_queries") as mock_files:
            mock_files.list_files = AsyncMock(return_value={
                "items": [], "total": 0, "page": 1, "size": 20, "pages": 0,
            })
            await list_files(
                page=1, size=20, status=None, region=None, brand=None,
                kb_target=None, job_id=None, source_id=None,
                folder_id=None, unfiled=True, search=None, db=db,
            )
        kwargs = mock_files.list_files.await_args.kwargs
        assert kwargs["folder_id"] is None
        assert kwargs["unfiled"] is True

    @pytest.mark.asyncio
    async def test_neither_param_set(self):
        db = AsyncMock()
        with patch("kb_manager.routes.files.file_queries") as mock_files:
            mock_files.list_files = AsyncMock(return_value={
                "items": [], "total": 0, "page": 1, "size": 20, "pages": 0,
            })
            await list_files(
                page=1, size=20, status=None, region=None, brand=None,
                kb_target=None, job_id=None, source_id=None,
                folder_id=None, unfiled=False, search=None, db=db,
            )
        kwargs = mock_files.list_files.await_args.kwargs
        assert kwargs["folder_id"] is None
        assert kwargs["unfiled"] is False


# ---------------------------------------------------------------------------
# PATCH /files/{id} — move a legacy (unfiled) file into a folder
# ---------------------------------------------------------------------------

def _make_legacy_file(**overrides) -> MagicMock:
    """Mock of a URL-ingested KBFile: folder_id=None, has s3_key."""
    defaults = {
        "id": uuid.uuid4(),
        "title": "Legacy URL Article",
        "md_content": "# Legacy\nbody",
        "source_url": "https://example.com/legacy",
        "region": "nam",
        "brand": "avis",
        "kb_target": "public",
        "language": "en",
        "status": "approved",
        "quality_verdict": "accepted",
        "quality_reasoning": "ok",
        "uniqueness_verdict": "unique",
        "uniqueness_reasoning": "no match",
        "category": "general",
        "visibility": "public",
        "tags": [],
        "s3_key": "public/avis/nam/en/legacy/legacy-url-article.md",
        "folder_id": None,
        "reviewed_by": None,
        "review_notes": None,
        "modify_date": None,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "similar_file_ids": None,
        "job_id": uuid.uuid4(),
        "sources": [],
    }
    defaults.update(overrides)
    f = MagicMock(spec=[])
    for k, v in defaults.items():
        setattr(f, k, v)
    return f


def _make_folder(*, kb_target="public") -> MagicMock:
    folder = MagicMock()
    folder.id = uuid.uuid4()
    folder.name = "Imported"
    folder.kb_target = kb_target
    return folder


def _make_request() -> MagicMock:
    request = MagicMock()
    request.app.state.s3_uploader = MagicMock()
    request.app.state.session_factory = MagicMock()
    request.app.state.bedrock_kb_client = MagicMock()
    return request


def _bg() -> MagicMock:
    bg = MagicMock()
    bg.add_task = MagicMock()
    return bg


class TestLegacyMoveIntoFolder:
    @pytest.mark.asyncio
    async def test_legacy_file_moved_into_matching_kb_target_folder(self):
        legacy = _make_legacy_file()
        target = _make_folder(kb_target="public")
        request = _make_request()
        bg = _bg()
        db = AsyncMock()

        with (
            patch("kb_manager.routes.files.file_queries") as mock_files,
            patch("kb_manager.routes.files.folder_queries") as mock_folders,
        ):
            mock_files.get_file = AsyncMock(side_effect=[legacy, legacy])
            mock_files.update_file = AsyncMock()
            mock_folders.get_folder = AsyncMock(return_value=target)

            result = await edit_file_metadata(
                legacy.id, FileMetadataEdit(folder_id=target.id),
                bg, request, db,
            )

        # folder_id update applied
        update_kwargs = mock_files.update_file.await_args.kwargs
        assert update_kwargs["folder_id"] == target.id
        # Cosmetic-style propagation (folder_path changed; key segments did not)
        assert bg.add_task.call_count == 1
        assert bg.add_task.call_args.args[0] is _resync_sidecar_only
        assert result.id == legacy.id

    @pytest.mark.asyncio
    async def test_legacy_file_cross_kb_target_rejected(self):
        legacy = _make_legacy_file(kb_target="public")
        target = _make_folder(kb_target="internal")
        request = _make_request()
        db = AsyncMock()

        with (
            patch("kb_manager.routes.files.file_queries") as mock_files,
            patch("kb_manager.routes.files.folder_queries") as mock_folders,
        ):
            mock_files.get_file = AsyncMock(return_value=legacy)
            mock_folders.get_folder = AsyncMock(return_value=target)
            with pytest.raises(HTTPException) as exc:
                await edit_file_metadata(
                    legacy.id, FileMetadataEdit(folder_id=target.id),
                    _bg(), request, db,
                )
        assert exc.value.status_code == 422
