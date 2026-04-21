"""In-memory SSE event bus.

Two layers:
1. Per-job channels — ``(job_id, channel)`` keyed subscriber queues
   for pipeline-internal progress tracking.
2. Global event stream — typed events with ``topic`` + ``event`` + payload,
   consumed by ``GET /api/v1/events/stream``.  UI subscribes once and
   filters client-side by topic.

A sentinel ``None`` value signals end-of-stream for per-job channels.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


class StreamManager:
    """In-memory SSE event bus with per-job channels and a global typed event stream."""

    def __init__(self) -> None:
        # Per-job channels: (job_id, channel) → list of subscriber queues
        self._channels: dict[tuple[str, str], list[asyncio.Queue]] = defaultdict(list)
        # Global event subscribers (for /events/stream)
        self._event_subscribers: list[asyncio.Queue] = []
        logger.info("📡 StreamManager initialised")

    # ------------------------------------------------------------------
    # Global typed event stream
    # ------------------------------------------------------------------

    def add_event_subscriber(self, queue: asyncio.Queue) -> None:
        self._event_subscribers.append(queue)
        logger.info("📡 Event subscriber added (total: %d)", len(self._event_subscribers))

    def remove_event_subscriber(self, queue: asyncio.Queue) -> None:
        try:
            self._event_subscribers.remove(queue)
        except ValueError:
            pass
        logger.info("📡 Event subscriber removed (total: %d)", len(self._event_subscribers))

    async def publish_event(
        self,
        topic: str,
        event: str,
        data: dict | None = None,
        **extra: object,
    ) -> None:
        """Publish a typed event to all global event subscribers.

        Event format:
            {"timestamp": ..., "topic": "worker", "event": "worker_started", "data": {...}}
        """
        entry = {
            "timestamp": time.time(),
            "topic": topic,
            "event": event,
            "data": {**(data or {}), **extra},
        }
        for queue in list(self._event_subscribers):
            try:
                queue.put_nowait(entry)
            except asyncio.QueueFull:
                pass

    # ------------------------------------------------------------------
    # Per-job channel API (used by pipeline for per-job SSE)
    # ------------------------------------------------------------------

    async def subscribe(
        self, job_id: str, channel: str
    ) -> AsyncGenerator[dict, None]:
        """Yield events for a *job_id* / *channel*.

        Blocks until events arrive. Terminates when a sentinel ``None``
        is received (pushed by :meth:`close_channel`).
        """
        key = (job_id, channel)
        queue: asyncio.Queue = asyncio.Queue()
        self._channels[key].append(queue)
        sub_count = len(self._channels[key])
        logger.info("📡 New subscriber for job=%s channel=%s (total subscribers: %d)",
                     job_id[:8], channel, sub_count)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    logger.debug("📡 Subscriber received sentinel for job=%s channel=%s", job_id[:8], channel)
                    break
                yield item
        finally:
            subscribers = self._channels.get(key)
            if subscribers is not None:
                try:
                    subscribers.remove(queue)
                except ValueError:
                    pass
            logger.debug("📡 Subscriber disconnected from job=%s channel=%s", job_id[:8], channel)

    async def publish(
        self, job_id: str, channel: str, event: str, data: dict
    ) -> None:
        """Push an event to all active subscriber queues for *job_id* / *channel*.

        Also broadcasts to global event stream as a ``progress`` topic event.
        """
        key = (job_id, channel)
        message = {"event": event, "data": data}
        for queue in list(self._channels.get(key, [])):
            await queue.put(message)

        # Mirror to global event stream
        await self.publish_event(
            topic="progress",
            event=event,
            data={**data, "job_id": job_id[:8], "channel": channel},
        )

    async def close_channel(self, job_id: str, channel: str) -> None:
        """Signal end-of-stream and clean up resources for *job_id* / *channel*."""
        key = (job_id, channel)
        subscribers = self._channels.pop(key, [])
        for queue in subscribers:
            await queue.put(None)
        logger.info("📡 Channel closed: job=%s channel=%s (%d subscribers notified)",
                     job_id[:8], channel, len(subscribers))
