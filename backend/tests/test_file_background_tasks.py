"""Tests for S3 upload and QA re-run background tasks in file routes (Task 7.2).

Validates Requirements 10.3, 10.5, 17.1, 17.2, 17.3.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kb_manager.routes.files import _upload_to_s3, _run_qa_background, _run_qa_sync


# ---------------------------------------------------------------------------
# _upload_to_s3 background task
# ---------------------------------------------------------------------------

class TestUploadToS3:
    """Tests for the S3 upload background task (Requirements 17.1, 17.2, 17.3)."""

    @pytest.mark.asyncio
    async def test_upload_success_updates_s3_key(self):
        """On successful upload, s3_key is written back to the file."""
        file_id = uuid.uuid4()
        mock_file = MagicMock(id=file_id)
        mock_s3 = MagicMock()
        mock_s3.upload.return_value = "public/brand/region/ns/file.md"

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory = MagicMock(return_value=mock_session_ctx)

        with patch("kb_manager.routes.files.file_queries") as mock_fq:
            mock_fq.get_file = AsyncMock(return_value=mock_file)
            mock_fq.update_file = AsyncMock()

            await _upload_to_s3(file_id, mock_s3, mock_session_factory)

            mock_s3.upload.assert_called_once_with(mock_file)
            mock_fq.update_file.assert_called_once_with(
                mock_db, file_id, s3_key="public/brand/region/ns/file.md"
            )
            mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_failure_does_not_update(self):
        """When S3 upload returns None, no s3_key update is made."""
        file_id = uuid.uuid4()
        mock_file = MagicMock(id=file_id)
        mock_s3 = MagicMock()
        mock_s3.upload.return_value = None

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory = MagicMock(return_value=mock_session_ctx)

        with patch("kb_manager.routes.files.file_queries") as mock_fq:
            mock_fq.get_file = AsyncMock(return_value=mock_file)
            mock_fq.update_file = AsyncMock()

            await _upload_to_s3(file_id, mock_s3, mock_session_factory)

            mock_s3.upload.assert_called_once_with(mock_file)
            mock_fq.update_file.assert_not_called()
            mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_upload_file_not_found(self):
        """When file is not found in DB, upload is skipped gracefully."""
        file_id = uuid.uuid4()
        mock_s3 = MagicMock()

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory = MagicMock(return_value=mock_session_ctx)

        with patch("kb_manager.routes.files.file_queries") as mock_fq:
            mock_fq.get_file = AsyncMock(return_value=None)

            await _upload_to_s3(file_id, mock_s3, mock_session_factory)

            mock_s3.upload.assert_not_called()

    @pytest.mark.asyncio
    async def test_upload_exception_is_caught(self):
        """Exceptions during upload don't propagate — they're logged."""
        file_id = uuid.uuid4()
        mock_s3 = MagicMock()
        mock_s3.upload.side_effect = Exception("boom")
        mock_file = MagicMock(id=file_id)

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory = MagicMock(return_value=mock_session_ctx)

        with patch("kb_manager.routes.files.file_queries") as mock_fq:
            mock_fq.get_file = AsyncMock(return_value=mock_file)
            # Should not raise
            await _upload_to_s3(file_id, mock_s3, mock_session_factory)


# ---------------------------------------------------------------------------
# _run_qa_background task
# ---------------------------------------------------------------------------

class TestRunQaBackground:
    """Tests for the QA re-run background task (Requirements 10.5)."""

    @pytest.mark.asyncio
    async def test_qa_rerun_updates_verdicts(self):
        """QA re-run updates quality/uniqueness verdicts and routes the file."""
        file_id = uuid.uuid4()
        mock_file = MagicMock(
            id=file_id,
            md_content="# Test\nSome content",
            title="Test",
            source_url="https://example.com",
            region="nam",
            brand="avis",
        )

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory = MagicMock(return_value=mock_session_ctx)

        mock_qa_result = MagicMock(
            quality_verdict="good",
            quality_reasoning="Well structured",
            uniqueness_verdict="unique",
            uniqueness_reasoning="No duplicates",
            similar_file_ids=[],
        )

        with (
            patch("kb_manager.routes.files.file_queries") as mock_fq,
            patch("kb_manager.agents.qa.QAAgent") as MockQA,
            patch("kb_manager.services.routing_matrix.route_file", return_value="approved") as mock_route,
        ):
            mock_fq.get_file = AsyncMock(return_value=mock_file)
            mock_fq.update_file = AsyncMock()
            mock_qa_instance = AsyncMock()
            mock_qa_instance.run = AsyncMock(return_value=mock_qa_result)
            MockQA.return_value = mock_qa_instance

            await _run_qa_background(file_id, mock_session_factory)

            mock_qa_instance.run.assert_called_once_with("# Test\nSome content")
            mock_route.assert_called_once_with("good", "unique", True)
            mock_fq.update_file.assert_called_once()
            mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_qa_rerun_file_not_found(self):
        """When file is not found, QA re-run is skipped gracefully."""
        file_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory = MagicMock(return_value=mock_session_ctx)

        with patch("kb_manager.routes.files.file_queries") as mock_fq:
            mock_fq.get_file = AsyncMock(return_value=None)

            await _run_qa_background(file_id, mock_session_factory)

            mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_qa_rerun_exception_is_caught(self):
        """Exceptions during QA re-run don't propagate."""
        file_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory = MagicMock(return_value=mock_session_ctx)

        with patch("kb_manager.routes.files.file_queries") as mock_fq:
            mock_fq.get_file = AsyncMock(side_effect=Exception("db error"))
            # Should not raise
            await _run_qa_background(file_id, mock_session_factory)


# ---------------------------------------------------------------------------
# _run_qa_sync
# ---------------------------------------------------------------------------

class TestRunQaSync:
    """Tests for the synchronous QA re-run (Requirement 10.6)."""

    @pytest.mark.asyncio
    async def test_sync_qa_updates_verdicts(self):
        """Synchronous QA updates verdicts and routes the file."""
        file_id = uuid.uuid4()
        mock_file = MagicMock(
            id=file_id,
            md_content="# Content",
            title="Title",
            source_url="https://example.com",
            region="emea",
            brand="budget",
        )
        mock_db = AsyncMock()

        mock_qa_result = MagicMock(
            quality_verdict="acceptable",
            quality_reasoning="Thin content",
            uniqueness_verdict="overlapping",
            uniqueness_reasoning="Some overlap",
            similar_file_ids=[],
        )

        with (
            patch("kb_manager.routes.files.file_queries") as mock_fq,
            patch("kb_manager.agents.qa.QAAgent") as MockQA,
            patch("kb_manager.services.routing_matrix.route_file", return_value="pending_review"),
        ):
            mock_fq.get_file = AsyncMock(return_value=mock_file)
            mock_fq.update_file = AsyncMock()
            mock_qa_instance = AsyncMock()
            mock_qa_instance.run = AsyncMock(return_value=mock_qa_result)
            MockQA.return_value = mock_qa_instance

            await _run_qa_sync(file_id, mock_db)

            mock_fq.update_file.assert_called_once()
            call_kwargs = mock_fq.update_file.call_args
            assert call_kwargs[1]["status"] == "pending_review"
            assert call_kwargs[1]["quality_verdict"] == "acceptable"

    @pytest.mark.asyncio
    async def test_sync_qa_file_not_found(self):
        """When file is not found, sync QA returns without error."""
        file_id = uuid.uuid4()
        mock_db = AsyncMock()

        with patch("kb_manager.routes.files.file_queries") as mock_fq:
            mock_fq.get_file = AsyncMock(return_value=None)
            mock_fq.update_file = AsyncMock()

            await _run_qa_sync(file_id, mock_db)

            mock_fq.update_file.assert_not_called()
