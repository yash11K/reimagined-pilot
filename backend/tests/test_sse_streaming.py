"""Tests for SSE streaming wiring in ingestion routes.

Validates Requirements 6.1, 6.2, 6.3, 6.4, 9.1, 9.2, 9.3, 9.4.
"""

import asyncio
import json

import pytest

from kb_manager.services.stream_manager import StreamManager
from kb_manager.routes.ingest import _sse_stream_generator, KEEPALIVE_INTERVAL


class _FakeAppState:
    """Minimal stand-in for FastAPI app.state."""

    def __init__(self, stream_manager: StreamManager) -> None:
        self.stream_manager = stream_manager


class _FakeApp:
    def __init__(self, stream_manager: StreamManager) -> None:
        self.state = _FakeAppState(stream_manager)


class _FakeRequest:
    """Minimal stand-in for a FastAPI Request."""

    def __init__(self, stream_manager: StreamManager) -> None:
        self.app = _FakeApp(stream_manager)


@pytest.fixture
def sm() -> StreamManager:
    return StreamManager()


@pytest.fixture
def fake_request(sm: StreamManager) -> _FakeRequest:
    return _FakeRequest(sm)


# ---------------------------------------------------------------------------
# Requirement 6.2 / 9.2 — SSE event format: event: {type}\ndata: {json}\n\n
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_event_format(sm: StreamManager, fake_request: _FakeRequest):
    """Events should be formatted as 'event: {type}\\ndata: {json}\\n\\n'."""
    import uuid

    job_id = uuid.uuid4()
    job_id_str = str(job_id)

    collected: list[str] = []

    async def consume():
        async for chunk in _sse_stream_generator(fake_request, job_id, "scout", "scout_complete"):
            collected.append(chunk)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)  # let generator register

    await sm.publish(job_id_str, "scout", "component_found", {"id": "comp_1", "type": "card"})
    await sm.publish(job_id_str, "scout", "scout_complete", {"job_id": job_id_str})
    await asyncio.sleep(0.01)
    await task

    assert len(collected) == 2

    # Verify format of first event
    assert collected[0].startswith("event: component_found\n")
    assert "data: " in collected[0]
    assert collected[0].endswith("\n\n")

    # Parse the data portion
    lines = collected[0].strip().split("\n")
    assert lines[0] == "event: component_found"
    data_line = lines[1]
    assert data_line.startswith("data: ")
    parsed = json.loads(data_line[6:])
    assert parsed == {"id": "comp_1", "type": "card"}


# ---------------------------------------------------------------------------
# Requirement 6.4 / 9.4 — Stream closes on terminal event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scout_stream_closes_on_scout_complete(sm: StreamManager, fake_request: _FakeRequest):
    """Scout stream should close after receiving scout_complete event."""
    import uuid

    job_id = uuid.uuid4()
    job_id_str = str(job_id)

    collected: list[str] = []

    async def consume():
        async for chunk in _sse_stream_generator(fake_request, job_id, "scout", "scout_complete"):
            collected.append(chunk)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)

    await sm.publish(job_id_str, "scout", "scouting_started", {"job_id": job_id_str})
    await sm.publish(job_id_str, "scout", "scout_complete", {"job_id": job_id_str, "summary": {}})
    # This event should NOT be received since stream closes on scout_complete
    await sm.publish(job_id_str, "scout", "extra_event", {"should": "not appear"})

    await asyncio.sleep(0.01)
    await task

    event_types = [c.split("\n")[0] for c in collected]
    assert "event: scouting_started" in event_types
    assert "event: scout_complete" in event_types
    assert "event: extra_event" not in event_types


@pytest.mark.asyncio
async def test_progress_stream_closes_on_job_complete(sm: StreamManager, fake_request: _FakeRequest):
    """Progress stream should close after receiving job_complete event."""
    import uuid

    job_id = uuid.uuid4()
    job_id_str = str(job_id)

    collected: list[str] = []

    async def consume():
        async for chunk in _sse_stream_generator(fake_request, job_id, "progress", "job_complete"):
            collected.append(chunk)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)

    await sm.publish(job_id_str, "progress", "extraction_started", {"job_id": job_id_str})
    await sm.publish(job_id_str, "progress", "job_complete", {"job_id": job_id_str, "files_created": 3})

    await asyncio.sleep(0.01)
    await task

    event_types = [c.split("\n")[0] for c in collected]
    assert "event: extraction_started" in event_types
    assert "event: job_complete" in event_types


# ---------------------------------------------------------------------------
# Requirement 6.4 — Stream closes on sentinel (None)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_closes_on_sentinel(sm: StreamManager, fake_request: _FakeRequest):
    """Stream should close when StreamManager sends sentinel (via close_channel)."""
    import uuid

    job_id = uuid.uuid4()
    job_id_str = str(job_id)

    collected: list[str] = []

    async def consume():
        async for chunk in _sse_stream_generator(fake_request, job_id, "scout", "scout_complete"):
            collected.append(chunk)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)

    await sm.publish(job_id_str, "scout", "scouting_started", {"job_id": job_id_str})
    await sm.close_channel(job_id_str, "scout")

    await asyncio.sleep(0.01)
    await task

    # Should have received the one event before sentinel
    assert len(collected) == 1
    assert "event: scouting_started" in collected[0]


# ---------------------------------------------------------------------------
# Requirement 6.3 / 9.3 — Keepalive every 15 seconds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_keepalive_sent_on_timeout(sm: StreamManager, fake_request: _FakeRequest, monkeypatch):
    """A keepalive comment should be sent when no events arrive within the interval."""
    import uuid
    import kb_manager.routes.ingest as ingest_module

    # Patch keepalive interval to a very short value for testing
    monkeypatch.setattr(ingest_module, "KEEPALIVE_INTERVAL", 0.05)

    job_id = uuid.uuid4()
    job_id_str = str(job_id)

    collected: list[str] = []

    async def consume():
        async for chunk in _sse_stream_generator(fake_request, job_id, "scout", "scout_complete"):
            collected.append(chunk)
            # After receiving keepalive, close the stream
            if chunk == ":keepalive\n\n":
                break

    task = asyncio.create_task(consume())
    # Wait long enough for the keepalive to fire
    await asyncio.sleep(0.15)

    # Cancel if still running (shouldn't be, but safety)
    if not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert ":keepalive\n\n" in collected


# ---------------------------------------------------------------------------
# Cleanup — subscriber queue removed after generator exits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscriber_cleanup_after_stream_ends(sm: StreamManager, fake_request: _FakeRequest):
    """After the SSE generator exits, the subscriber queue should be removed."""
    import uuid

    job_id = uuid.uuid4()
    job_id_str = str(job_id)
    key = (job_id_str, "scout")

    async def consume():
        async for _ in _sse_stream_generator(fake_request, job_id, "scout", "scout_complete"):
            pass

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)

    # Should have one subscriber
    assert len(sm._channels.get(key, [])) == 1

    await sm.close_channel(job_id_str, "scout")
    await asyncio.sleep(0.01)
    await task

    # After stream ends, subscriber should be cleaned up
    subs = sm._channels.get(key, [])
    assert len(subs) == 0
