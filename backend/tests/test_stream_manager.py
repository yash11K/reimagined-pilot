"""Unit tests for Stream Manager — validates Requirements 13.1–13.4."""

import asyncio

import pytest

from kb_manager.services.stream_manager import StreamManager


@pytest.fixture
def sm() -> StreamManager:
    return StreamManager()


# ---------------------------------------------------------------------------
# Requirement 13.1 — Separate event channels per job_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_channel_isolation(sm: StreamManager):
    """Events published to job A's channel must not appear in job B's channel."""
    collected_a: list[dict] = []
    collected_b: list[dict] = []

    async def consume(job_id: str, channel: str, dest: list[dict]):
        async for event in sm.subscribe(job_id, channel):
            dest.append(event)

    task_a = asyncio.create_task(consume("job-a", "scout", collected_a))
    task_b = asyncio.create_task(consume("job-b", "scout", collected_b))
    await asyncio.sleep(0)  # let subscribers register

    await sm.publish("job-a", "scout", "ping", {"v": 1})
    await sm.publish("job-b", "scout", "pong", {"v": 2})

    await sm.close_channel("job-a", "scout")
    await sm.close_channel("job-b", "scout")
    await asyncio.gather(task_a, task_b)

    assert collected_a == [{"event": "ping", "data": {"v": 1}}]
    assert collected_b == [{"event": "pong", "data": {"v": 2}}]


# ---------------------------------------------------------------------------
# Requirement 13.2 — Fan-out to all active subscribers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fan_out_to_multiple_subscribers(sm: StreamManager):
    """All subscribers of the same channel receive the same event."""
    results_1: list[dict] = []
    results_2: list[dict] = []

    async def consume(dest: list[dict]):
        async for event in sm.subscribe("job-1", "progress"):
            dest.append(event)

    t1 = asyncio.create_task(consume(results_1))
    t2 = asyncio.create_task(consume(results_2))
    await asyncio.sleep(0)

    await sm.publish("job-1", "progress", "step", {"n": 42})
    await sm.close_channel("job-1", "progress")
    await asyncio.gather(t1, t2)

    assert results_1 == [{"event": "step", "data": {"n": 42}}]
    assert results_2 == [{"event": "step", "data": {"n": 42}}]


# ---------------------------------------------------------------------------
# Requirement 13.3 — Late subscriber sees only new events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_late_subscriber_sees_only_new_events(sm: StreamManager):
    """A subscriber that joins after some events should not see old events."""
    # Publish an event before anyone subscribes
    await sm.publish("job-x", "scout", "early", {"seq": 0})

    collected: list[dict] = []

    async def consume(dest: list[dict]):
        async for event in sm.subscribe("job-x", "scout"):
            dest.append(event)

    task = asyncio.create_task(consume(collected))
    await asyncio.sleep(0)  # let subscriber register

    await sm.publish("job-x", "scout", "late", {"seq": 1})
    await sm.close_channel("job-x", "scout")
    await task

    # Should only contain the event published after subscription
    assert collected == [{"event": "late", "data": {"seq": 1}}]


# ---------------------------------------------------------------------------
# Requirement 13.4 — Cleanup after close_channel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_channel_cleans_up(sm: StreamManager):
    """After close_channel, internal data structures should not hold the channel."""
    collected: list[dict] = []

    async def consume(dest: list[dict]):
        async for event in sm.subscribe("job-z", "scout"):
            dest.append(event)

    task = asyncio.create_task(consume(collected))
    await asyncio.sleep(0)

    await sm.close_channel("job-z", "scout")
    await task

    # The channel key should be removed from internal structures
    assert ("job-z", "scout") not in sm._channels


# ---------------------------------------------------------------------------
# Edge: publish to channel with no subscribers is a no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_no_subscribers(sm: StreamManager):
    """Publishing to a channel with no subscribers should not raise."""
    await sm.publish("ghost", "scout", "noop", {"x": 1})


# ---------------------------------------------------------------------------
# Edge: close_channel on non-existent channel is a no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_nonexistent_channel(sm: StreamManager):
    """Closing a channel that was never opened should not raise."""
    await sm.close_channel("nope", "progress")


# ---------------------------------------------------------------------------
# Multiple events delivered in order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_events_delivered_in_order(sm: StreamManager):
    """Events should be delivered in the order they were published."""
    collected: list[dict] = []

    async def consume(dest: list[dict]):
        async for event in sm.subscribe("job-ord", "progress"):
            dest.append(event)

    task = asyncio.create_task(consume(collected))
    await asyncio.sleep(0)

    for i in range(5):
        await sm.publish("job-ord", "progress", "step", {"i": i})
    await sm.close_channel("job-ord", "progress")
    await task

    assert [e["data"]["i"] for e in collected] == [0, 1, 2, 3, 4]


# ---------------------------------------------------------------------------
# Scout and progress channels are independent for the same job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scout_and_progress_independent(sm: StreamManager):
    """Scout and progress channels for the same job are independent."""
    scout_events: list[dict] = []
    progress_events: list[dict] = []

    async def consume(job_id: str, channel: str, dest: list[dict]):
        async for event in sm.subscribe(job_id, channel):
            dest.append(event)

    t1 = asyncio.create_task(consume("job-dual", "scout", scout_events))
    t2 = asyncio.create_task(consume("job-dual", "progress", progress_events))
    await asyncio.sleep(0)

    await sm.publish("job-dual", "scout", "s_evt", {"s": 1})
    await sm.publish("job-dual", "progress", "p_evt", {"p": 2})

    await sm.close_channel("job-dual", "scout")
    await sm.close_channel("job-dual", "progress")
    await asyncio.gather(t1, t2)

    assert scout_events == [{"event": "s_evt", "data": {"s": 1}}]
    assert progress_events == [{"event": "p_evt", "data": {"p": 2}}]
