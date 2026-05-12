"""Tests for the /files/upload route validation + wiring (M2).

Mocks folder/source/job/file query modules and invokes the handler directly,
matching the style of other route-layer tests in this suite. Pipeline-level
behaviour (enrichment + QA + routing) is covered separately in
test_upload_pipeline.py.
"""

import io
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from kb_manager.routes.files import (
    _decode_markdown,
    _folder_defaults,
    _validate_upload,
    upload_file,
)


def _make_upload(filename: str, body: bytes) -> UploadFile:
    """Build an UploadFile backed by an in-memory buffer."""
    return UploadFile(filename=filename, file=io.BytesIO(body))


def _make_folder(**kwargs) -> MagicMock:
    folder = MagicMock()
    folder.id = kwargs.get("id", uuid.uuid4())
    folder.name = kwargs.get("name", "docs")
    folder.parent_folder_id = kwargs.get("parent_folder_id")
    folder.kb_target = kwargs.get("kb_target", "public")
    folder.default_brand = kwargs.get("default_brand")
    folder.default_region = kwargs.get("default_region")
    folder.default_language = kwargs.get("default_language")
    return folder


def _make_request_with_pipeline() -> MagicMock:
    """FastAPI Request with an attached pipeline state."""
    request = MagicMock()
    request.app.state.pipeline = MagicMock()
    return request


# ---------------------------------------------------------------------------
# Pure-function helpers
# ---------------------------------------------------------------------------

class TestValidateUpload:
    def test_rejects_missing_filename(self):
        f = UploadFile(filename="", file=io.BytesIO(b"x"))
        with pytest.raises(HTTPException) as exc:
            _validate_upload(f, b"x")
        assert exc.value.status_code == 422

    def test_rejects_disallowed_extension(self):
        f = _make_upload("note.pdf", b"x")
        with pytest.raises(HTTPException) as exc:
            _validate_upload(f, b"x")
        assert exc.value.status_code == 415

    def test_rejects_empty_file(self):
        f = _make_upload("a.md", b"")
        with pytest.raises(HTTPException) as exc:
            _validate_upload(f, b"")
        assert exc.value.status_code == 422

    def test_rejects_oversize(self):
        f = _make_upload("a.md", b"x")
        big = b"x" * (10 * 1024 * 1024 + 1)
        with pytest.raises(HTTPException) as exc:
            _validate_upload(f, big)
        assert exc.value.status_code == 413

    def test_accepts_md_markdown_txt(self):
        for name in ("a.md", "A.MD", "x.Markdown", "y.txt"):
            f = _make_upload(name, b"hi")
            _validate_upload(f, b"hi")  # no raise


class TestDecodeMarkdown:
    def test_decodes_utf8(self):
        assert _decode_markdown("héllo".encode("utf-8"), "a.md") == "héllo"

    def test_rejects_non_utf8(self):
        with pytest.raises(HTTPException) as exc:
            _decode_markdown(b"\xff\xfe\xff", "a.md")
        assert exc.value.status_code == 422


class TestFolderDefaults:
    def test_returns_only_set_fields(self):
        folder = _make_folder(default_brand="avis", default_region=None)
        assert _folder_defaults(folder) == {"brand": "avis"}

    def test_empty_when_no_defaults(self):
        assert _folder_defaults(_make_folder()) == {}

    def test_all_three_fields(self):
        folder = _make_folder(
            default_brand="budget",
            default_region="emea",
            default_language="en",
        )
        assert _folder_defaults(folder) == {
            "brand": "budget", "region": "emea", "language": "en",
        }


# ---------------------------------------------------------------------------
# upload_file route handler
# ---------------------------------------------------------------------------

class TestUploadFileRoute:
    @pytest.mark.asyncio
    async def test_folder_not_found_returns_404(self):
        request = _make_request_with_pipeline()
        bg = MagicMock()
        bg.add_task = MagicMock()
        db = AsyncMock()
        f = _make_upload("doc.md", b"# Hello\n")
        with patch("kb_manager.routes.files.folder_queries") as mock_folders:
            mock_folders.get_folder = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc:
                await upload_file(
                    request=request, background_tasks=bg,
                    file=f, folder_id=uuid.uuid4(), title=None, db=db,
                )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_happy_path_creates_source_job_file_and_schedules_task(self):
        folder = _make_folder(default_brand="avis", default_region="nam")
        body = b"# Refueling Policy\nContent here."
        f = _make_upload("refueling-policy.md", body)
        request = _make_request_with_pipeline()
        bg = MagicMock()
        bg.add_task = MagicMock()
        db = AsyncMock()

        source = MagicMock(id=uuid.uuid4())
        job = MagicMock(id=uuid.uuid4())
        kb_file = MagicMock(
            id=uuid.uuid4(), status="pending_review", title="refueling-policy",
        )

        with (
            patch("kb_manager.routes.files.folder_queries") as mock_folders,
            patch("kb_manager.routes.files.source_queries") as mock_sources,
            patch("kb_manager.routes.files.job_queries") as mock_jobs,
            patch("kb_manager.routes.files.file_queries") as mock_files,
        ):
            mock_folders.get_folder = AsyncMock(return_value=folder)
            mock_sources.get_source_by_url = AsyncMock(return_value=None)
            mock_sources.create_source = AsyncMock(return_value=source)
            mock_jobs.create_job = AsyncMock(return_value=job)
            mock_files.create_file = AsyncMock(return_value=kb_file)
            mock_files.link_source_to_file = AsyncMock()

            result = await upload_file(
                request=request, background_tasks=bg,
                file=f, folder_id=folder.id, title=None, db=db,
            )

        # Source URL is content-addressable
        src_url = mock_sources.create_source.await_args.kwargs["url"]
        assert src_url.startswith("upload://")
        assert src_url.endswith("/refueling-policy.md")
        # Job is synthetic completed
        job_kwargs = mock_jobs.create_job.await_args.kwargs
        assert job_kwargs["status"] == "completed"
        assert job_kwargs["progress_pct"] == 100
        # File inherits folder defaults + sets folder_id + pending_review
        file_kwargs = mock_files.create_file.await_args.kwargs
        assert file_kwargs["folder_id"] == folder.id
        assert file_kwargs["brand"] == "avis"
        assert file_kwargs["region"] == "nam"
        assert file_kwargs["status"] == "pending_review"
        assert file_kwargs["kb_target"] == "public"
        # Junction link created
        mock_files.link_source_to_file.assert_awaited_once_with(
            db, source.id, kb_file.id,
        )
        # Background pipeline task scheduled with folder defaults
        bg.add_task.assert_called_once()
        args = bg.add_task.call_args.args
        assert args[1] == kb_file.id
        assert args[3] == {"brand": "avis", "region": "nam"}
        # Commit happens after all writes
        db.commit.assert_awaited()

        assert result.file_id == kb_file.id
        assert result.source_id == source.id
        assert result.job_id == job.id
        assert result.folder_id == folder.id
        assert result.status == "pending_review"
        assert result.deduped is False

    @pytest.mark.asyncio
    async def test_dedupe_flag_set_when_source_existed(self):
        folder = _make_folder()
        f = _make_upload("a.md", b"hello")
        request = _make_request_with_pipeline()
        bg = MagicMock()
        bg.add_task = MagicMock()
        db = AsyncMock()

        with (
            patch("kb_manager.routes.files.folder_queries") as mock_folders,
            patch("kb_manager.routes.files.source_queries") as mock_sources,
            patch("kb_manager.routes.files.job_queries") as mock_jobs,
            patch("kb_manager.routes.files.file_queries") as mock_files,
        ):
            mock_folders.get_folder = AsyncMock(return_value=folder)
            mock_sources.get_source_by_url = AsyncMock(
                return_value=MagicMock(id=uuid.uuid4()),
            )
            mock_sources.create_source = AsyncMock(
                return_value=MagicMock(id=uuid.uuid4()),
            )
            mock_jobs.create_job = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
            mock_files.create_file = AsyncMock(
                return_value=MagicMock(
                    id=uuid.uuid4(), status="pending_review", title="a",
                ),
            )
            mock_files.link_source_to_file = AsyncMock()

            result = await upload_file(
                request=request, background_tasks=bg,
                file=f, folder_id=folder.id, title=None, db=db,
            )
        assert result.deduped is True

    @pytest.mark.asyncio
    async def test_explicit_title_wins_over_filename_stem(self):
        folder = _make_folder()
        f = _make_upload("doc.md", b"hello")
        request = _make_request_with_pipeline()
        bg = MagicMock()
        bg.add_task = MagicMock()
        db = AsyncMock()
        with (
            patch("kb_manager.routes.files.folder_queries") as mock_folders,
            patch("kb_manager.routes.files.source_queries") as mock_sources,
            patch("kb_manager.routes.files.job_queries") as mock_jobs,
            patch("kb_manager.routes.files.file_queries") as mock_files,
        ):
            mock_folders.get_folder = AsyncMock(return_value=folder)
            mock_sources.get_source_by_url = AsyncMock(return_value=None)
            mock_sources.create_source = AsyncMock(
                return_value=MagicMock(id=uuid.uuid4()),
            )
            mock_jobs.create_job = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
            mock_files.create_file = AsyncMock(
                return_value=MagicMock(
                    id=uuid.uuid4(), status="pending_review", title="Refueling",
                ),
            )
            mock_files.link_source_to_file = AsyncMock()

            await upload_file(
                request=request, background_tasks=bg,
                file=f, folder_id=folder.id,
                title="Refueling", db=db,
            )
        file_kwargs = mock_files.create_file.await_args.kwargs
        assert file_kwargs["title"] == "Refueling"
