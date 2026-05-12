"""Tests for the upload-side enrichment + QA pipeline (M2).

Covers:
  - ``MetadataEnricher._apply_folder_defaults`` overrides LLM output.
  - ``Pipeline.process_upload`` runs enricher → QA → routing → optional S3
    upload, and rejects the file on unexpected errors.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kb_manager.agents.metadata_enricher import (
    EnrichedMetadata,
    MetadataEnricher,
)
from kb_manager.services.pipeline import Pipeline


# ---------------------------------------------------------------------------
# MetadataEnricher._apply_folder_defaults
# ---------------------------------------------------------------------------

class TestFolderDefaultsOverride:
    def test_no_defaults_returns_unchanged(self):
        meta = EnrichedMetadata(
            title="t", filename="t", brand="avis", category="faq",
        )
        out = MetadataEnricher._apply_folder_defaults(meta, None)
        assert out.brand == "avis"

    def test_empty_dict_returns_unchanged(self):
        meta = EnrichedMetadata(
            title="t", filename="t", brand="avis", category="faq",
        )
        out = MetadataEnricher._apply_folder_defaults(meta, {})
        assert out.brand == "avis"

    def test_folder_brand_overrides_llm_brand(self):
        meta = EnrichedMetadata(
            title="t", filename="t", brand="unknown", category="faq",
        )
        out = MetadataEnricher._apply_folder_defaults(
            meta, {"brand": "budget"},
        )
        assert out.brand == "budget"

    def test_unknown_field_ignored(self):
        meta = EnrichedMetadata(
            title="t", filename="t", brand="avis", category="faq",
        )
        out = MetadataEnricher._apply_folder_defaults(
            meta, {"not_a_field": "x"},
        )
        assert out.brand == "avis"
        assert not hasattr(out, "not_a_field")

    def test_empty_value_does_not_override(self):
        meta = EnrichedMetadata(
            title="t", filename="t", brand="avis", category="faq",
        )
        out = MetadataEnricher._apply_folder_defaults(
            meta, {"brand": ""},
        )
        assert out.brand == "avis"


# ---------------------------------------------------------------------------
# Pipeline.process_upload
# ---------------------------------------------------------------------------

def _session_factory_with(db: MagicMock) -> MagicMock:
    """Build a session_factory that yields the given async db mock."""
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=ctx)
    return factory


def _make_pipeline(*, s3_mock: MagicMock, kb_mock: MagicMock | None) -> Pipeline:
    """Construct a Pipeline with mocked services for isolated unit tests."""
    stream = MagicMock()
    versioning = MagicMock()
    db = AsyncMock()
    session_factory = _session_factory_with(db)
    pipeline = Pipeline.__new__(Pipeline)
    pipeline._stream = stream
    pipeline._s3 = s3_mock
    pipeline._versioning = versioning
    pipeline._session_factory = session_factory
    pipeline._kb_client = kb_mock
    pipeline._settings = MagicMock()
    # Expose the db mock for assertions.
    pipeline.__db = db  # type: ignore[attr-defined]
    return pipeline


class TestProcessUpload:
    @pytest.mark.asyncio
    async def test_approves_clean_upload_and_triggers_kb_sync(self):
        file_id = uuid.uuid4()
        kb_file = MagicMock(
            id=file_id,
            md_content="# Refueling Policy\nContent here.",
            title="refueling-policy",
            source_url="upload://abc/refueling-policy.md",
            region="nam",
            language="en",
            folder_id=None,  # legacy/unfiled path — no folder context lookup
        )
        s3 = MagicMock()
        s3.upload = AsyncMock(return_value="public/avis/nam/en/ns/file.md")
        kb_client = MagicMock()
        kb_client.start_sync = AsyncMock(return_value="ingestion-1")

        pipeline = _make_pipeline(s3_mock=s3, kb_mock=kb_client)
        enriched = EnrichedMetadata(
            title="Refueling Policy",
            filename="refueling-policy",
            brand="avis",
            category="policy",
            visibility="public",
            tags=["fuel", "policy"],
        )
        qa_result = MagicMock(
            quality_verdict="accepted",
            quality_reasoning="ok",
            uniqueness_verdict="unique",
            uniqueness_reasoning="no match",
            similar_file_ids=[],
        )

        with (
            patch("kb_manager.services.pipeline.file_queries") as mock_files,
            patch("kb_manager.services.pipeline.MetadataEnricher") as mock_me,
            patch(
                "kb_manager.services.pipeline.run_qa_and_uniqueness",
                new=AsyncMock(return_value=qa_result),
            ),
            patch(
                "kb_manager.services.pipeline.route_file",
                return_value="approved",
            ),
        ):
            mock_files.get_file = AsyncMock(side_effect=[kb_file, kb_file])
            mock_files.update_file = AsyncMock()
            mock_me.return_value.run = AsyncMock(return_value=enriched)

            await pipeline.process_upload(
                file_id, folder_defaults={"brand": "avis", "region": "nam"},
            )

        # MetadataEnricher.run received folder_defaults
        run_kwargs = mock_me.return_value.run.await_args.kwargs
        assert run_kwargs["folder_defaults"] == {"brand": "avis", "region": "nam"}

        # File updated with enriched metadata first
        first_update_kwargs = mock_files.update_file.await_args_list[0].kwargs
        assert first_update_kwargs["brand"] == "avis"
        assert first_update_kwargs["category"] == "policy"
        assert first_update_kwargs["region"] == "nam"
        assert first_update_kwargs["tags"] == ["fuel", "policy"]

        # Then routed → approved + verdicts stored
        verdict_update = mock_files.update_file.await_args_list[1].kwargs
        assert verdict_update["status"] == "approved"
        assert verdict_update["quality_verdict"] == "accepted"
        assert verdict_update["uniqueness_verdict"] == "unique"

        # S3 upload + KB sync triggered (no folder context for unfiled file)
        s3.upload.assert_awaited_once_with(
            kb_file, namespace=None, folder_path=None,
        )
        kb_client.start_sync.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_approved_upload_in_folder_resolves_path_and_namespace(self):
        file_id = uuid.uuid4()
        folder_id = uuid.uuid4()
        kb_file = MagicMock(
            id=file_id,
            md_content="# Doc\nBody.",
            title="doc",
            source_url="upload://h/doc.md",
            region="nam",
            language="en",
            folder_id=folder_id,
        )
        # NOTE: MagicMock's `name` constructor kwarg sets the repr name, not
        # an attribute — assign explicitly so folder.name is the string we
        # want the pipeline to read.
        folder = MagicMock(id=folder_id)
        folder.name = "Policies"
        s3 = MagicMock()
        s3.upload = AsyncMock(return_value="public/avis/nam/en/Policies/doc.md")
        kb_client = MagicMock()
        kb_client.start_sync = AsyncMock(return_value="i-1")
        pipeline = _make_pipeline(s3_mock=s3, kb_mock=kb_client)

        enriched = EnrichedMetadata(
            title="Doc", filename="doc", brand="avis", category="policy",
        )
        qa_result = MagicMock(
            quality_verdict="accepted", quality_reasoning="",
            uniqueness_verdict="unique", uniqueness_reasoning="",
            similar_file_ids=[],
        )

        with (
            patch("kb_manager.services.pipeline.file_queries") as mock_files,
            patch(
                "kb_manager.services.pipeline.resolve_upload_context",
                new=AsyncMock(return_value=("Policies", "Docs/Policies")),
            ),
            patch("kb_manager.services.pipeline.MetadataEnricher") as mock_me,
            patch(
                "kb_manager.services.pipeline.run_qa_and_uniqueness",
                new=AsyncMock(return_value=qa_result),
            ),
            patch(
                "kb_manager.services.pipeline.route_file",
                return_value="approved",
            ),
        ):
            mock_files.get_file = AsyncMock(side_effect=[kb_file, kb_file])
            mock_files.update_file = AsyncMock()
            mock_me.return_value.run = AsyncMock(return_value=enriched)

            await pipeline.process_upload(
                file_id, folder_defaults={"brand": "avis"},
            )

        # Folder context flows into the upload call
        s3.upload.assert_awaited_once_with(
            kb_file, namespace="Policies", folder_path="Docs/Policies",
        )

    @pytest.mark.asyncio
    async def test_incomplete_metadata_does_not_auto_approve(self):
        file_id = uuid.uuid4()
        # No region from folder, no source_url stem → metadata_complete=False
        kb_file = MagicMock(
            id=file_id, md_content="x", title="t",
            source_url="upload://h/t.md", region=None, language=None,
        )
        s3 = MagicMock()
        s3.upload = AsyncMock()
        kb_client = MagicMock()
        kb_client.start_sync = AsyncMock()

        pipeline = _make_pipeline(s3_mock=s3, kb_mock=kb_client)

        enriched = EnrichedMetadata(
            title="t", filename="t", brand="unknown", category="general",
        )
        qa_result = MagicMock(
            quality_verdict="accepted", quality_reasoning="",
            uniqueness_verdict="unique", uniqueness_reasoning="",
            similar_file_ids=[],
        )

        captured_args: list[tuple] = []

        def capture_route(q, u, complete):
            captured_args.append((q, u, complete))
            return "pending_review" if not complete else "approved"

        with (
            patch("kb_manager.services.pipeline.file_queries") as mock_files,
            patch("kb_manager.services.pipeline.MetadataEnricher") as mock_me,
            patch(
                "kb_manager.services.pipeline.run_qa_and_uniqueness",
                new=AsyncMock(return_value=qa_result),
            ),
            patch(
                "kb_manager.services.pipeline.route_file",
                side_effect=capture_route,
            ),
        ):
            mock_files.get_file = AsyncMock(return_value=kb_file)
            mock_files.update_file = AsyncMock()
            mock_me.return_value.run = AsyncMock(return_value=enriched)

            await pipeline.process_upload(file_id, folder_defaults=None)

        # route_file received metadata_complete=False because region/brand
        # are empty/'unknown'
        assert captured_args[0][2] is False
        # No S3 / sync side-effect on non-approved status
        s3.upload.assert_not_awaited()
        kb_client.start_sync.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_file_missing_returns_silently(self):
        s3 = MagicMock()
        s3.upload = AsyncMock()
        pipeline = _make_pipeline(s3_mock=s3, kb_mock=None)

        with patch("kb_manager.services.pipeline.file_queries") as mock_files:
            mock_files.get_file = AsyncMock(return_value=None)
            # No exception expected; nothing to do.
            await pipeline.process_upload(uuid.uuid4())

        s3.upload.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exception_marks_file_rejected(self):
        file_id = uuid.uuid4()
        kb_file = MagicMock(
            id=file_id, md_content="x", title="t",
            source_url="upload://h/t.md", region="nam", language="en",
        )
        s3 = MagicMock()
        s3.upload = AsyncMock()
        pipeline = _make_pipeline(s3_mock=s3, kb_mock=None)

        with (
            patch("kb_manager.services.pipeline.file_queries") as mock_files,
            patch("kb_manager.services.pipeline.MetadataEnricher") as mock_me,
        ):
            mock_files.get_file = AsyncMock(return_value=kb_file)
            mock_files.update_file = AsyncMock()
            mock_me.return_value.run = AsyncMock(side_effect=RuntimeError("boom"))

            # process_upload must not propagate — it's a background task.
            await pipeline.process_upload(file_id)

        # The error path calls update_file(status="rejected", ...)
        reject_call = [
            c for c in mock_files.update_file.await_args_list
            if c.kwargs.get("status") == "rejected"
        ]
        assert reject_call, "Expected file to be marked rejected on failure"
