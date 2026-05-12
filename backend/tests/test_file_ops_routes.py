"""Tests for the PATCH and COPY routes added in M4.

Mocks query modules and invokes route handlers directly. Background-task
behaviour is asserted through ``BackgroundTasks.add_task`` calls; the
underlying ``_recompute_after_edit`` / ``_resync_sidecar_only`` /
``_upload_to_s3`` helpers are exercised separately.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from kb_manager.routes.files import (
    _recompute_after_edit,
    _resync_sidecar_only,
    copy_file,
    edit_file_metadata,
)
from kb_manager.schemas.files import CopyRequest, FileMetadataEdit


def _make_file(**overrides) -> MagicMock:
    """KBFile mock with the union of attributes the routes touch."""
    defaults = {
        "id": uuid.uuid4(),
        "title": "Original",
        "md_content": "# Doc\nbody",
        "source_url": "upload://abc/original.md",
        "region": "nam",
        "brand": "avis",
        "kb_target": "public",
        "language": "en",
        "status": "approved",
        "quality_verdict": "accepted",
        "quality_reasoning": "ok",
        "uniqueness_verdict": "unique",
        "uniqueness_reasoning": "no match",
        "category": "policy",
        "visibility": "public",
        "tags": ["fuel"],
        "s3_key": "public/avis/nam/en/ns/original.md",
        "folder_id": uuid.uuid4(),
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
    folder.name = "Policies"
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


# ---------------------------------------------------------------------------
# PATCH /files/{file_id}
# ---------------------------------------------------------------------------

class TestPatchFileMetadata:
    @pytest.mark.asyncio
    async def test_404_when_file_missing(self):
        request = _make_request()
        db = AsyncMock()
        with patch("kb_manager.routes.files.file_queries") as mock_files:
            mock_files.get_file = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc:
                await edit_file_metadata(
                    uuid.uuid4(), FileMetadataEdit(title="x"),
                    _bg(), request, db,
                )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_cosmetic_edit_triggers_sidecar_resync_only(self):
        file = _make_file()
        request = _make_request()
        db = AsyncMock()
        bg = _bg()
        with patch("kb_manager.routes.files.file_queries") as mock_files:
            mock_files.get_file = AsyncMock(side_effect=[file, file])
            mock_files.update_file = AsyncMock()

            result = await edit_file_metadata(
                file.id, FileMetadataEdit(category="faq"),
                bg, request, db,
            )

        assert result.id == file.id
        # 1 background task, and it's the sidecar helper.
        assert bg.add_task.call_count == 1
        assert bg.add_task.call_args.args[0] is _resync_sidecar_only

    @pytest.mark.asyncio
    async def test_key_segment_edit_triggers_recompute(self):
        file = _make_file(brand="avis")
        request = _make_request()
        db = AsyncMock()
        bg = _bg()
        with patch("kb_manager.routes.files.file_queries") as mock_files:
            mock_files.get_file = AsyncMock(side_effect=[file, file])
            mock_files.update_file = AsyncMock()

            await edit_file_metadata(
                file.id, FileMetadataEdit(brand="budget"),
                bg, request, db,
            )

        assert bg.add_task.call_count == 1
        assert bg.add_task.call_args.args[0] is _recompute_after_edit
        # old_s3_key snapshot is passed in
        assert bg.add_task.call_args.args[2] == file.s3_key

    @pytest.mark.asyncio
    async def test_no_s3_key_skips_background_task(self):
        # File was never uploaded — pending_review without s3_key. No
        # S3 work to schedule regardless of which field changed.
        file = _make_file(s3_key=None, status="pending_review")
        request = _make_request()
        db = AsyncMock()
        bg = _bg()
        with patch("kb_manager.routes.files.file_queries") as mock_files:
            mock_files.get_file = AsyncMock(side_effect=[file, file])
            mock_files.update_file = AsyncMock()
            await edit_file_metadata(
                file.id, FileMetadataEdit(brand="budget"),
                bg, request, db,
            )
        bg.add_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_folder_move_within_kb_target(self):
        file = _make_file(kb_target="public", brand="avis")
        target = _make_folder(kb_target="public")
        request = _make_request()
        db = AsyncMock()
        bg = _bg()
        with (
            patch("kb_manager.routes.files.file_queries") as mock_files,
            patch("kb_manager.routes.files.folder_queries") as mock_folders,
        ):
            mock_files.get_file = AsyncMock(side_effect=[file, file])
            mock_files.update_file = AsyncMock()
            mock_folders.get_folder = AsyncMock(return_value=target)

            await edit_file_metadata(
                file.id, FileMetadataEdit(folder_id=target.id),
                bg, request, db,
            )

        # Folder move alone = sidecar resync (folder_path attribute changed)
        assert bg.add_task.call_args.args[0] is _resync_sidecar_only

    @pytest.mark.asyncio
    async def test_folder_move_cross_kb_target_forbidden(self):
        file = _make_file(kb_target="public")
        target = _make_folder(kb_target="internal")
        request = _make_request()
        db = AsyncMock()
        with (
            patch("kb_manager.routes.files.file_queries") as mock_files,
            patch("kb_manager.routes.files.folder_queries") as mock_folders,
        ):
            mock_files.get_file = AsyncMock(return_value=file)
            mock_folders.get_folder = AsyncMock(return_value=target)
            with pytest.raises(HTTPException) as exc:
                await edit_file_metadata(
                    file.id, FileMetadataEdit(folder_id=target.id),
                    _bg(), request, db,
                )
        assert exc.value.status_code == 422
        assert "Cross-kb_target" in exc.value.detail

    @pytest.mark.asyncio
    async def test_folder_move_target_not_found(self):
        file = _make_file()
        request = _make_request()
        db = AsyncMock()
        target_id = uuid.uuid4()
        with (
            patch("kb_manager.routes.files.file_queries") as mock_files,
            patch("kb_manager.routes.files.folder_queries") as mock_folders,
        ):
            mock_files.get_file = AsyncMock(return_value=file)
            mock_folders.get_folder = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc:
                await edit_file_metadata(
                    file.id, FileMetadataEdit(folder_id=target_id),
                    _bg(), request, db,
                )
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# POST /files/{file_id}/copy
# ---------------------------------------------------------------------------

class TestCopyFile:
    @pytest.mark.asyncio
    async def test_404_when_source_missing(self):
        request = _make_request()
        db = AsyncMock()
        with patch("kb_manager.routes.files.file_queries") as mock_files:
            mock_files.get_file = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc:
                await copy_file(
                    uuid.uuid4(), CopyRequest(folder_id=uuid.uuid4()),
                    _bg(), request, db,
                )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_kb_target_copy_forbidden(self):
        src = _make_file(kb_target="public")
        target = _make_folder(kb_target="internal")
        request = _make_request()
        db = AsyncMock()
        with (
            patch("kb_manager.routes.files.file_queries") as mock_files,
            patch("kb_manager.routes.files.folder_queries") as mock_folders,
        ):
            mock_files.get_file = AsyncMock(return_value=src)
            mock_folders.get_folder = AsyncMock(return_value=target)
            with pytest.raises(HTTPException) as exc:
                await copy_file(
                    src.id, CopyRequest(folder_id=target.id),
                    _bg(), request, db,
                )
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_copy_creates_new_file_with_overlapping_verdict(self):
        src = _make_file(kb_target="public", status="approved")
        target = _make_folder(kb_target="public")
        request = _make_request()
        db = AsyncMock()
        bg = _bg()

        source_id = uuid.uuid4()
        # The route runs a SELECT through db.execute — return a one-row result.
        exec_result = MagicMock()
        exec_result.all = MagicMock(return_value=[(source_id,)])
        db.execute = AsyncMock(return_value=exec_result)

        new_job = MagicMock(id=uuid.uuid4())
        new_file = _make_file(
            id=uuid.uuid4(),
            status=src.status,
            uniqueness_verdict="overlapping",
            uniqueness_reasoning=f"Copy of file {src.id}",
            similar_file_ids=[src.id],
            folder_id=target.id,
        )

        with (
            patch("kb_manager.routes.files.file_queries") as mock_files,
            patch("kb_manager.routes.files.folder_queries") as mock_folders,
            patch("kb_manager.routes.files.job_queries") as mock_jobs,
        ):
            mock_files.get_file = AsyncMock(return_value=src)
            mock_folders.get_folder = AsyncMock(return_value=target)
            mock_jobs.create_job = AsyncMock(return_value=new_job)
            mock_files.create_file = AsyncMock(return_value=new_file)
            mock_files.link_source_to_file = AsyncMock()

            result = await copy_file(
                src.id, CopyRequest(folder_id=target.id),
                bg, request, db,
            )

        # Synthetic job inherits the source's primary source_id
        assert mock_jobs.create_job.await_args.kwargs["source_id"] == source_id
        assert mock_jobs.create_job.await_args.kwargs["status"] == "completed"

        # New file: forced overlapping + lineage, target folder, same content
        create_kwargs = mock_files.create_file.await_args.kwargs
        assert create_kwargs["folder_id"] == target.id
        assert create_kwargs["uniqueness_verdict"] == "overlapping"
        assert create_kwargs["similar_file_ids"] == [src.id]
        assert create_kwargs["md_content"] == src.md_content
        assert create_kwargs["kb_target"] == src.kb_target

        # Source linkage preserved
        mock_files.link_source_to_file.assert_awaited_once_with(
            db, source_id, new_file.id,
        )

        # Approved source → background S3 upload scheduled for the copy
        assert bg.add_task.call_count == 1
        assert result.id == new_file.id
        assert result.uniqueness_verdict == "overlapping"

    @pytest.mark.asyncio
    async def test_copy_unapproved_skips_s3_upload(self):
        src = _make_file(status="pending_review", s3_key=None)
        target = _make_folder()
        request = _make_request()
        db = AsyncMock()
        bg = _bg()
        source_id = uuid.uuid4()
        exec_result = MagicMock()
        exec_result.all = MagicMock(return_value=[(source_id,)])
        db.execute = AsyncMock(return_value=exec_result)

        with (
            patch("kb_manager.routes.files.file_queries") as mock_files,
            patch("kb_manager.routes.files.folder_queries") as mock_folders,
            patch("kb_manager.routes.files.job_queries") as mock_jobs,
        ):
            mock_files.get_file = AsyncMock(return_value=src)
            mock_folders.get_folder = AsyncMock(return_value=target)
            mock_jobs.create_job = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
            mock_files.create_file = AsyncMock(return_value=_make_file(
                folder_id=target.id, status="pending_review",
                uniqueness_verdict="overlapping",
                similar_file_ids=[src.id],
            ))
            mock_files.link_source_to_file = AsyncMock()

            await copy_file(
                src.id, CopyRequest(folder_id=target.id),
                bg, request, db,
            )

        bg.add_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_copy_rejects_when_source_has_no_linkage(self):
        src = _make_file()
        target = _make_folder()
        request = _make_request()
        db = AsyncMock()
        exec_result = MagicMock()
        exec_result.all = MagicMock(return_value=[])
        db.execute = AsyncMock(return_value=exec_result)

        with (
            patch("kb_manager.routes.files.file_queries") as mock_files,
            patch("kb_manager.routes.files.folder_queries") as mock_folders,
        ):
            mock_files.get_file = AsyncMock(return_value=src)
            mock_folders.get_folder = AsyncMock(return_value=target)
            with pytest.raises(HTTPException) as exc:
                await copy_file(
                    src.id, CopyRequest(folder_id=target.id),
                    _bg(), request, db,
                )
        assert exc.value.status_code == 409
