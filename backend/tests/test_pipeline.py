"""Unit tests for Pipeline Orchestrator — validates Requirements 14.1–14.7."""

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set required env vars before importing anything that triggers get_settings()
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")

from kb_manager.config import get_settings
from kb_manager.services.pipeline import Pipeline
from kb_manager.services.stream_manager import StreamManager


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Clear the lru_cache on get_settings between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeComponent:
    id: str = "comp_0"
    component_type: str = "card"
    title: str | None = "Test Title"
    text_snippet: str | None = "Some snippet"
    links: list[str] = field(default_factory=list)


@dataclass
class FakeRawLink:
    url: str = "https://example.com/page"
    anchor_text: str | None = "Learn More"
    context: str | None = "Teaser text"


@dataclass
class FakeDiscoveryResult:
    components: list = field(default_factory=list)
    classified_links: list = field(default_factory=list)


@dataclass
class FakeTriageResult:
    classification: str = "expansion"
    reason: str = "Teaser card links to full article"
    has_sub_links: bool = False
    sub_link_count: int = 0


@dataclass
class FakeClassifiedLink:
    url: str = "https://example.com/sub.model.json"
    anchor_text: str | None = "Learn More"
    context: str | None = "Teaser text"
    classification: str = "certain"
    reason: str = "Content card links to detail page"


@dataclass
class FakeExtractedFile:
    title: str = "Test File"
    md_content: str = "---\ntitle: Test\n---\n# Content"
    source_url: str | None = "https://example.com/page"
    content_type: str | None = "article"
    region: str | None = "nam"
    brand: str | None = "avis"
    merged_from_urls: list[str] = field(default_factory=list)


@dataclass
class FakeQAResult:
    quality_verdict: str = "good"
    quality_reasoning: str = "Well-structured content"
    uniqueness_verdict: str = "unique"
    uniqueness_reasoning: str = "No overlap found"
    similar_file_ids: list[str] = field(default_factory=list)


@dataclass
class FakeSource:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    identifier: str = "https://example.com/page.model.json"
    region: str | None = "nam"
    brand: str | None = "avis"
    kb_target: str = "public"


@dataclass
class FakeJob:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    source_id: uuid.UUID = field(default_factory=uuid.uuid4)
    status: str = "scouting"
    steering_prompt: str | None = None
    scout_summary: dict | None = None
    source: Any = None


@dataclass
class FakeKBFile:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    title: str = "Test File"
    md_content: str = "# Content"
    status: str = "pending_review"
    kb_target: str = "public"
    brand: str | None = "avis"
    region: str | None = "nam"
    source_url: str | None = "https://example.com"
    s3_key: str | None = None


@dataclass
class FakeContentLink:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    job_id: uuid.UUID = field(default_factory=uuid.uuid4)
    target_url: str = "https://example.com/linked"
    anchor_text: str | None = "Learn More"
    classification: str = "expansion"
    classification_reason: str | None = "Teaser"
    status: str = "auto_queued"
    has_sub_links: bool = False
    sub_link_count: int = 0


def _make_pipeline(stream_manager=None):
    """Create a Pipeline with mocked dependencies."""
    sm = stream_manager or StreamManager()
    s3 = MagicMock()
    s3.upload = MagicMock(return_value="public/avis/nam/test/file.md")
    s3.delete = MagicMock(return_value=True)
    versioning = AsyncMock()
    versioning.check_and_supersede = AsyncMock(return_value="process")
    session_factory = AsyncMock()
    return Pipeline(
        stream_manager=sm,
        s3_uploader=s3,
        versioning_service=versioning,
        session_factory=session_factory,
    )


# ---------------------------------------------------------------------------
# Requirement 14.5 — Pipeline failure sets job to failed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scout_failure_sets_job_failed():
    """When scout phase raises, job status should be set to 'failed' with error message."""
    sm = StreamManager()
    pipeline = _make_pipeline(sm)

    error_events: list[dict] = []

    async def collect_errors():
        async for event in sm.subscribe(str(uuid.uuid4()), "scout"):
            if event["event"] == "error":
                error_events.append(event)

    job_id = uuid.uuid4()
    job_id_str = str(job_id)

    # Collect events
    scout_events: list[dict] = []

    async def collect():
        async for event in sm.subscribe(job_id_str, "scout"):
            scout_events.append(event)

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)

    # Mock httpx to raise an error
    with patch("kb_manager.services.pipeline.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client_cls.return_value = mock_client

        # Mock session factory
        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        pipeline._session_factory = MagicMock(return_value=mock_session_ctx)

        with patch("kb_manager.services.pipeline.job_queries") as mock_jobs:
            mock_jobs.update_job = AsyncMock()
            mock_jobs.update_job_status = AsyncMock()
            mock_jobs.get_job = AsyncMock(return_value=None)

            await pipeline.run_scout(job_id, "https://example.com/page.model.json")

            # Verify job was set to failed
            mock_jobs.update_job_status.assert_called_once_with(
                mock_db, job_id, "failed", error_message="Connection refused"
            )

    await task

    # Verify error event was published
    error_evts = [e for e in scout_events if e["event"] == "error"]
    assert len(error_evts) == 1
    assert "Connection refused" in error_evts[0]["data"]["message"]


@pytest.mark.asyncio
async def test_process_failure_sets_job_failed():
    """When process phase raises, job status should be set to 'failed'."""
    sm = StreamManager()
    pipeline = _make_pipeline(sm)

    job_id = uuid.uuid4()
    job_id_str = str(job_id)

    progress_events: list[dict] = []

    async def collect():
        async for event in sm.subscribe(job_id_str, "progress"):
            progress_events.append(event)

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)

    # Mock session factory to raise
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(side_effect=Exception("DB connection lost"))
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
    pipeline._session_factory = MagicMock(return_value=mock_session_ctx)

    # For _fail_job, we need a working session
    fail_db = AsyncMock()
    fail_db.commit = AsyncMock()
    fail_session_ctx = AsyncMock()
    fail_session_ctx.__aenter__ = AsyncMock(return_value=fail_db)
    fail_session_ctx.__aexit__ = AsyncMock(return_value=False)

    call_count = 0

    def session_side_effect():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_session_ctx
        return fail_session_ctx

    pipeline._session_factory = MagicMock(side_effect=session_side_effect)

    from kb_manager.schemas.ingest import ConfirmRequest

    confirmation = ConfirmRequest()

    with patch("kb_manager.services.pipeline.job_queries") as mock_jobs:
        mock_jobs.update_job_status = AsyncMock()

        await pipeline.run_process(job_id, confirmation)

        mock_jobs.update_job_status.assert_called_once_with(
            fail_db, job_id, "failed", error_message="DB connection lost"
        )

    await task

    error_evts = [e for e in progress_events if e["event"] == "error"]
    assert len(error_evts) == 1


# ---------------------------------------------------------------------------
# Requirement 14.1 — Scout phase stores results and sets awaiting_confirmation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scout_stores_results_and_sets_status():
    """Scout phase should store content_links, scout_summary, and set status."""
    sm = StreamManager()
    pipeline = _make_pipeline(sm)

    job_id = uuid.uuid4()
    job_id_str = str(job_id)

    scout_events: list[dict] = []

    async def collect():
        async for event in sm.subscribe(job_id_str, "scout"):
            scout_events.append(event)

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)

    # Mock httpx
    with patch("kb_manager.services.pipeline.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {":items": {}, ":itemsOrder": []}
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        # Mock agents
        with patch("kb_manager.services.pipeline.DiscoveryAgent") as mock_da_cls:

            mock_da = AsyncMock()
            mock_da.run = AsyncMock(return_value=FakeDiscoveryResult(
                components=[FakeComponent()],
                classified_links=[],
            ))
            mock_da_cls.return_value = mock_da

            # Mock DB
            mock_db = AsyncMock()
            mock_db.commit = AsyncMock()
            mock_session_ctx = AsyncMock()
            mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
            pipeline._session_factory = MagicMock(return_value=mock_session_ctx)

            with patch("kb_manager.services.pipeline.job_queries") as mock_jobs, \
                 patch("kb_manager.services.pipeline.source_queries") as mock_sources, \
                 patch("kb_manager.services.pipeline.extract_links_deterministic", return_value=[]):
                mock_jobs.update_job = AsyncMock()
                mock_jobs.get_job = AsyncMock(return_value=FakeJob(source=FakeSource()))
                mock_sources.mark_scouted = AsyncMock()

                # Also mock run_process to prevent it from running
                with patch.object(pipeline, "run_process", new=AsyncMock()):
                    await pipeline.run_scout(
                        job_id, "https://example.com/page.model.json"
                    )

                # Verify job was updated with status
                assert mock_jobs.update_job.call_count == 2
                # First call: progress_pct=10 at scout start
                # Second call: status="processing", progress_pct=40 after scout
                last_call_kwargs = mock_jobs.update_job.call_args_list[-1]
                assert last_call_kwargs[1]["status"] == "processing"
                assert last_call_kwargs[1]["progress_pct"] == 40

    await task

    # Verify SSE events were published
    event_types = [e["event"] for e in scout_events]
    assert "scouting_started" in event_types
    assert "component_found" in event_types
    assert "scout_complete" in event_types


# ---------------------------------------------------------------------------
# Requirement 14.3 — Scout publishes SSE events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scout_publishes_sse_events():
    """Scout phase should publish all required SSE event types."""
    sm = StreamManager()
    pipeline = _make_pipeline(sm)

    job_id = uuid.uuid4()
    job_id_str = str(job_id)

    scout_events: list[dict] = []

    async def collect():
        async for event in sm.subscribe(job_id_str, "scout"):
            scout_events.append(event)

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)

    with patch("kb_manager.services.pipeline.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {":items": {}, ":itemsOrder": []}
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        fake_classified_link = FakeClassifiedLink(url="https://example.com/en/sub.model.json")
        with patch("kb_manager.services.pipeline.DiscoveryAgent") as mock_da_cls, \
             patch("kb_manager.services.pipeline.extract_links_deterministic", return_value=[
                 {"url": "https://example.com/en/sub.model.json", "anchor_text": "Learn More", "context": "card ctaLink"},
             ]):

            mock_da = AsyncMock()
            mock_da.run = AsyncMock(return_value=FakeDiscoveryResult(
                components=[FakeComponent()],
                classified_links=[fake_classified_link],
            ))
            mock_da_cls.return_value = mock_da

            mock_db = AsyncMock()
            mock_db.commit = AsyncMock()
            # Mock db.execute for the dedup URL query in scout
            mock_exec_result = MagicMock()
            mock_exec_result.all.return_value = []
            mock_db.execute = AsyncMock(return_value=mock_exec_result)
            mock_session_ctx = AsyncMock()
            mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
            pipeline._session_factory = MagicMock(return_value=mock_session_ctx)

            fake_source = FakeSource()
            fake_job = FakeJob(source=fake_source)
            fake_discovered_source = FakeSource()

            with patch("kb_manager.services.pipeline.job_queries") as mock_jobs, \
                 patch("kb_manager.services.pipeline.source_queries") as mock_sources, \
                 patch("kb_manager.services.pipeline.queue_queries") as mock_queue:
                mock_jobs.update_job = AsyncMock()
                mock_jobs.update_job_status = AsyncMock()
                mock_jobs.get_job = AsyncMock(return_value=fake_job)
                mock_sources.mark_scouted = AsyncMock()
                mock_sources.get_source_by_url = AsyncMock(return_value=None)
                mock_sources.create_source = AsyncMock(return_value=fake_discovered_source)
                mock_queue.add_to_queue = AsyncMock()

                with patch.object(pipeline, "run_process", new=AsyncMock()):
                    await pipeline.run_scout(
                        job_id, "https://example.com/en/page.model.json"
                    )

    await task

    event_types = [e["event"] for e in scout_events]
    assert "scouting_started" in event_types
    assert "component_found" in event_types
    assert "link_found" in event_types
    assert "link_classified" in event_types
    assert "scout_complete" in event_types


# ---------------------------------------------------------------------------
# Requirement 14.7 — Individual file failures don't fail the job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_individual_file_failure_continues_processing():
    """Individual file failures should mark file as rejected, not fail the job."""
    sm = StreamManager()
    pipeline = _make_pipeline(sm)

    job_id = uuid.uuid4()
    job_id_str = str(job_id)

    progress_events: list[dict] = []

    async def collect():
        async for event in sm.subscribe(job_id_str, "progress"):
            progress_events.append(event)

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)

    fake_source = FakeSource()
    fake_job = FakeJob(
        source=fake_source,
        scout_summary={
            "components": [{"id": "comp_0", "type": "card", "title": "Test", "snippet": "...", "included": True}],
            "links": [],
            "summary": {},
        },
    )

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
    pipeline._session_factory = MagicMock(return_value=mock_session_ctx)

    fake_kb_file = FakeKBFile()

    with patch("kb_manager.services.pipeline.job_queries") as mock_jobs, \
         patch("kb_manager.services.pipeline.link_queries") as mock_links, \
         patch("kb_manager.services.pipeline.file_queries") as mock_files, \
         patch("kb_manager.services.pipeline.ExtractorAgent") as mock_ext_cls, \
         patch("kb_manager.services.pipeline.QAAgent") as mock_qa_cls, \
         patch("kb_manager.services.pipeline.httpx.AsyncClient") as mock_client_cls:

        mock_jobs.get_job = AsyncMock(return_value=fake_job)
        mock_jobs.update_job = AsyncMock()
        mock_jobs.update_job_status = AsyncMock()
        mock_links.get_links_by_job = AsyncMock(return_value=[])

        mock_files.create_file = AsyncMock(return_value=fake_kb_file)
        mock_files.update_file = AsyncMock()
        mock_files.get_file = AsyncMock(return_value=fake_kb_file)

        # Mock httpx for source page fetch (versioning check)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_source_resp = MagicMock()
        mock_source_resp.status_code = 200
        mock_source_resp.raise_for_status = MagicMock()
        mock_source_resp.json.return_value = {":items": {}, ":itemsOrder": []}
        mock_client.get = AsyncMock(return_value=mock_source_resp)
        mock_client_cls.return_value = mock_client

        # Mock DB execute for superseded file query in _check_versioning_and_cleanup
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Extractor returns one file
        mock_ext = AsyncMock()
        mock_ext.run = AsyncMock(return_value=[FakeExtractedFile()])
        mock_ext_cls.return_value = mock_ext

        # QA agent raises an error
        mock_qa = AsyncMock()
        mock_qa.run = AsyncMock(side_effect=Exception("QA service unavailable"))
        mock_qa_cls.return_value = mock_qa

        from kb_manager.schemas.ingest import ConfirmRequest

        await pipeline.run_process(job_id, ConfirmRequest())

        # Job should still be completed, not failed
        mock_jobs.update_job_status.assert_called_once_with(
            mock_db, job_id, "completed"
        )

    await task

    # Should have a job_complete event
    event_types = [e["event"] for e in progress_events]
    assert "job_complete" in event_types
    # The file failure should show as rejected in the counts
    complete_evt = next(e for e in progress_events if e["event"] == "job_complete")
    assert complete_evt["data"]["files_rejected"] >= 1


# ---------------------------------------------------------------------------
# Concurrency control — semaphore limits concurrent jobs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_has_no_semaphore():
    """Pipeline no longer owns concurrency — the queue worker does."""
    pipeline = _make_pipeline()
    assert not hasattr(pipeline, "_semaphore")


# ---------------------------------------------------------------------------
# Upload process — basic flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_process_completes():
    """Upload process should parse files, run QA, and complete."""
    sm = StreamManager()
    pipeline = _make_pipeline(sm)

    job_id = uuid.uuid4()
    job_id_str = str(job_id)

    progress_events: list[dict] = []

    async def collect():
        async for event in sm.subscribe(job_id_str, "progress"):
            progress_events.append(event)

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)

    fake_source = FakeSource()
    fake_job = FakeJob(source=fake_source)
    fake_kb_file = FakeKBFile()

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
    pipeline._session_factory = MagicMock(return_value=mock_session_ctx)

    # Create a fake UploadFile
    mock_upload = AsyncMock()
    mock_upload.read = AsyncMock(return_value=b"# Hello World\nSome content here.")
    mock_upload.filename = "test-doc.md"

    with patch("kb_manager.services.pipeline.job_queries") as mock_jobs, \
         patch("kb_manager.services.pipeline.file_queries") as mock_files, \
         patch("kb_manager.services.pipeline.QAAgent") as mock_qa_cls:

        mock_jobs.get_job = AsyncMock(return_value=fake_job)
        mock_jobs.update_job = AsyncMock()
        mock_jobs.update_job_status = AsyncMock()

        mock_files.create_file = AsyncMock(return_value=fake_kb_file)
        mock_files.update_file = AsyncMock()
        mock_files.get_file = AsyncMock(return_value=fake_kb_file)

        mock_qa = AsyncMock()
        mock_qa.run = AsyncMock(return_value=FakeQAResult())
        mock_qa_cls.return_value = mock_qa

        await pipeline.run_upload_process(job_id, [mock_upload])

        mock_jobs.update_job_status.assert_called_once_with(
            mock_db, job_id, "completed"
        )

    await task

    event_types = [e["event"] for e in progress_events]
    assert "extraction_started" in event_types
    assert "job_complete" in event_types


# ---------------------------------------------------------------------------
# Requirement 18.1–18.4 — Versioning wired into pipeline process phase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_versioning_skip_skips_source_page():
    """When versioning returns 'skip' for the source page, extraction should be skipped."""
    sm = StreamManager()
    pipeline = _make_pipeline(sm)
    # Configure versioning to return "skip"
    pipeline._versioning.check_and_supersede = AsyncMock(return_value="skip")

    job_id = uuid.uuid4()
    job_id_str = str(job_id)

    progress_events: list[dict] = []

    async def collect():
        async for event in sm.subscribe(job_id_str, "progress"):
            progress_events.append(event)

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)

    fake_source = FakeSource()
    fake_job = FakeJob(
        source=fake_source,
        scout_summary={
            "components": [{"id": "comp_0", "type": "card", "title": "Test", "snippet": "...", "included": True}],
            "links": [],
            "summary": {},
        },
    )

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
    pipeline._session_factory = MagicMock(return_value=mock_session_ctx)

    # Mock DB execute for superseded file query
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = None
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("kb_manager.services.pipeline.job_queries") as mock_jobs, \
         patch("kb_manager.services.pipeline.link_queries") as mock_links, \
         patch("kb_manager.services.pipeline.ExtractorAgent") as mock_ext_cls, \
         patch("kb_manager.services.pipeline.QAAgent") as mock_qa_cls, \
         patch("kb_manager.services.pipeline.httpx.AsyncClient") as mock_client_cls:

        mock_jobs.get_job = AsyncMock(return_value=fake_job)
        mock_jobs.update_job = AsyncMock()
        mock_jobs.update_job_status = AsyncMock()
        mock_links.get_links_by_job = AsyncMock(return_value=[])

        # Mock httpx for source page fetch
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {":items": {}, ":itemsOrder": []}
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        mock_ext = AsyncMock()
        mock_ext.run = AsyncMock(return_value=[])
        mock_ext_cls.return_value = mock_ext

        mock_qa = AsyncMock()
        mock_qa_cls.return_value = mock_qa

        from kb_manager.schemas.ingest import ConfirmRequest

        await pipeline.run_process(job_id, ConfirmRequest())

        # Extractor should NOT have been called since source was skipped
        mock_ext.run.assert_not_called()

        # Job should still complete
        mock_jobs.update_job_status.assert_called_once_with(
            mock_db, job_id, "completed"
        )

    await task

    event_types = [e["event"] for e in progress_events]
    assert "job_complete" in event_types
    complete_evt = next(e for e in progress_events if e["event"] == "job_complete")
    assert complete_evt["data"]["files_created"] == 0


@pytest.mark.asyncio
async def test_versioning_process_deletes_old_s3_key():
    """When versioning returns 'process' and a superseded file has an S3 key, it should be deleted."""
    sm = StreamManager()
    pipeline = _make_pipeline(sm)
    # Configure versioning to return "process"
    pipeline._versioning.check_and_supersede = AsyncMock(return_value="process")

    job_id = uuid.uuid4()
    job_id_str = str(job_id)

    progress_events: list[dict] = []

    async def collect():
        async for event in sm.subscribe(job_id_str, "progress"):
            progress_events.append(event)

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)

    fake_source = FakeSource()
    fake_job = FakeJob(
        source=fake_source,
        scout_summary={
            "components": [{"id": "comp_0", "type": "card", "title": "Test", "snippet": "...", "included": True}],
            "links": [],
            "summary": {},
        },
    )
    fake_kb_file = FakeKBFile()

    # Create a superseded file with an S3 key
    superseded_file = FakeKBFile(
        status="superseded",
        s3_key="public/avis/nam/old-page/old-file.md",
    )

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
    pipeline._session_factory = MagicMock(return_value=mock_session_ctx)

    # Mock DB execute to return the superseded file
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = superseded_file
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("kb_manager.services.pipeline.job_queries") as mock_jobs, \
         patch("kb_manager.services.pipeline.link_queries") as mock_links, \
         patch("kb_manager.services.pipeline.file_queries") as mock_files, \
         patch("kb_manager.services.pipeline.ExtractorAgent") as mock_ext_cls, \
         patch("kb_manager.services.pipeline.QAAgent") as mock_qa_cls, \
         patch("kb_manager.services.pipeline.httpx.AsyncClient") as mock_client_cls:

        mock_jobs.get_job = AsyncMock(return_value=fake_job)
        mock_jobs.update_job = AsyncMock()
        mock_jobs.update_job_status = AsyncMock()
        mock_links.get_links_by_job = AsyncMock(return_value=[])

        mock_files.create_file = AsyncMock(return_value=fake_kb_file)
        mock_files.update_file = AsyncMock()
        mock_files.get_file = AsyncMock(return_value=fake_kb_file)

        # Mock httpx for source page fetch
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {":items": {}, ":itemsOrder": []}
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        mock_ext = AsyncMock()
        mock_ext.run = AsyncMock(return_value=[FakeExtractedFile()])
        mock_ext_cls.return_value = mock_ext

        mock_qa = AsyncMock()
        mock_qa.run = AsyncMock(return_value=FakeQAResult())
        mock_qa_cls.return_value = mock_qa

        from kb_manager.schemas.ingest import ConfirmRequest

        await pipeline.run_process(job_id, ConfirmRequest())

        # S3 delete should have been called with the old file's key
        pipeline._s3.delete.assert_called_with("public/avis/nam/old-page/old-file.md")

    await task


@pytest.mark.asyncio
async def test_versioning_skip_skips_sibling_link():
    """When versioning returns 'skip' for a sibling link, that link should be skipped."""
    sm = StreamManager()
    pipeline = _make_pipeline(sm)

    # First call (source page) returns "process", second call (sibling) returns "skip"
    pipeline._versioning.check_and_supersede = AsyncMock(
        side_effect=["process", "skip"]
    )

    job_id = uuid.uuid4()
    job_id_str = str(job_id)

    progress_events: list[dict] = []

    async def collect():
        async for event in sm.subscribe(job_id_str, "progress"):
            progress_events.append(event)

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)

    fake_source = FakeSource()
    fake_job = FakeJob(
        source=fake_source,
        scout_summary={
            "components": [{"id": "comp_0", "type": "card", "title": "Test", "snippet": "...", "included": True}],
            "links": [],
            "summary": {},
        },
    )
    fake_kb_file = FakeKBFile()

    sibling_link = FakeContentLink(
        classification="sibling",
        target_url="https://example.com/sibling-page",
    )

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
    pipeline._session_factory = MagicMock(return_value=mock_session_ctx)

    # Mock DB execute for superseded file query (no superseded files)
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = None
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("kb_manager.services.pipeline.job_queries") as mock_jobs, \
         patch("kb_manager.services.pipeline.link_queries") as mock_links, \
         patch("kb_manager.services.pipeline.file_queries") as mock_files, \
         patch("kb_manager.services.pipeline.ExtractorAgent") as mock_ext_cls, \
         patch("kb_manager.services.pipeline.QAAgent") as mock_qa_cls, \
         patch("kb_manager.services.pipeline.httpx.AsyncClient") as mock_client_cls:

        mock_jobs.get_job = AsyncMock(return_value=fake_job)
        mock_jobs.update_job = AsyncMock()
        mock_jobs.update_job_status = AsyncMock()
        mock_links.get_links_by_job = AsyncMock(return_value=[sibling_link])
        mock_links.update_link = AsyncMock()

        mock_files.create_file = AsyncMock(return_value=fake_kb_file)
        mock_files.update_file = AsyncMock()
        mock_files.get_file = AsyncMock(return_value=fake_kb_file)

        # Mock httpx
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {":items": {}, ":itemsOrder": []}
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        mock_ext = AsyncMock()
        # Source page extraction returns one file, sibling should be skipped
        mock_ext.run = AsyncMock(return_value=[FakeExtractedFile()])
        mock_ext_cls.return_value = mock_ext

        mock_qa = AsyncMock()
        mock_qa.run = AsyncMock(return_value=FakeQAResult())
        mock_qa_cls.return_value = mock_qa

        from kb_manager.schemas.ingest import ConfirmRequest

        await pipeline.run_process(job_id, ConfirmRequest())

        # Extractor should have been called only once (for source page, not sibling)
        assert mock_ext.run.call_count == 1

        # Sibling link should NOT have been marked as ingested
        mock_links.update_link.assert_not_called()

    await task


def test_extract_modify_date_from_top_level():
    """_extract_modify_date should extract date from top-level AEM keys."""
    from datetime import datetime, timezone

    aem_json = {"jcr:lastModified": "2024-06-15T10:30:00Z", ":items": {}}
    result = Pipeline._extract_modify_date(aem_json)
    assert result == datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc)


def test_extract_modify_date_from_jcr_content():
    """_extract_modify_date should extract date from nested jcr:content."""
    from datetime import datetime, timezone

    aem_json = {
        "jcr:content": {"cq:lastModified": "2024-01-20T08:00:00+00:00"},
        ":items": {},
    }
    result = Pipeline._extract_modify_date(aem_json)
    assert result == datetime(2024, 1, 20, 8, 0, 0, tzinfo=timezone.utc)


def test_extract_modify_date_fallback():
    """_extract_modify_date should fall back to current time when no date found."""
    from datetime import datetime, timezone

    aem_json = {":items": {}, ":itemsOrder": []}
    result = Pipeline._extract_modify_date(aem_json)
    # Should be very close to now
    assert (datetime.now(timezone.utc) - result).total_seconds() < 2
