# Stream Manager — SSE Event Bus

**File:** `kb_manager/services/stream_manager.py`

---

## Overview

The StreamManager is an in-memory Server-Sent Events (SSE) event bus that provides real-time progress tracking for the UI. It has two layers: per-job channels for pipeline-specific progress, and a global typed event stream for dashboard-level updates.

---

## Architecture

```
                    StreamManager
                         │
          ┌──────────────┼──────────────┐
          │                             │
    Per-Job Channels              Global Event Stream
    (job_id, channel)             (all subscribers)
          │                             │
    ┌─────┴─────┐                ┌──────┴──────┐
    │ scout     │                │ subscriber 1 │
    │ progress  │                │ subscriber 2 │
    └───────────┘                └──────────────┘
```

---

## Layer 1: Per-Job Channels

Keyed by `(job_id, channel)` where channel is `"scout"` or `"progress"`.

### Publishing
```python
await stream_manager.publish(job_id, "scout", "component_found", {...})
await stream_manager.publish(job_id, "progress", "file_created", {...})
```

### Subscribing
Routes create subscriber queues and yield SSE-formatted strings:
```python
# GET /api/v1/ingest/{job_id}/scout-stream
queue = asyncio.Queue()
stream_manager._channels[(job_id, "scout")].append(queue)
# yield items from queue as SSE
```

### End-of-Stream
```python
await stream_manager.close_channel(job_id, "scout")
# Sends None sentinel to all subscribers → they close the SSE connection
```

### Keepalive
SSE endpoints send `:keepalive\n\n` comments every 15 seconds to prevent connection timeout.

---

## Layer 2: Global Typed Event Stream

A single stream consumed by `GET /api/v1/events/stream`. The UI subscribes once and filters client-side by topic.

### Publishing
```python
await stream_manager.publish_event(
    topic="queue",
    event="item_completed",
    worker_id=0,
    queue_item_id="abc",
    url="https://...",
)
```

### Event Format
```json
{
    "topic": "queue",
    "event": "item_completed",
    "ts": 1714200000.123,
    "worker_id": 0,
    "queue_item_id": "abc",
    "url": "https://..."
}
```

### Topics & Events

| Topic | Events |
|---|---|
| `worker` | `worker_started`, `worker_idle` |
| `queue` | `item_completed`, `item_failed`, `item_requeued`, `item_reclaimed` |
| `progress` | `phase_changed` |

---

## Memory Management

- Per-job channels are cleaned up when `close_channel()` is called (end of scout/process phase)
- Global event subscribers are removed when the SSE connection closes
- No persistence — events are fire-and-forget. If no subscriber is listening, events are dropped.
