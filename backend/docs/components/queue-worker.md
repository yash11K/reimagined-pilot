# Queue Worker — Background Processing Engine

**File:** `kb_manager/services/queue_worker.py`

---

## Overview

The QueueWorker is a background asyncio task that continuously polls the `queue_items` table, claims work, and runs the full ingestion pipeline. It provides bounded concurrency, heartbeat-based liveness detection, stale item recovery, and exponential backoff retries.

---

## Class: `QueueWorker`

### Constructor

```python
QueueWorker(
    pipeline: Pipeline,
    stream_manager: StreamManager,
    session_factory: async_sessionmaker[AsyncSession],
)
```

### Configuration (from Settings)

| Setting | Default | Purpose |
|---|---|---|
| `MAX_CONCURRENT_JOBS` | 3 | Semaphore size — max parallel items |
| `QUEUE_POLL_INTERVAL` | 3s | Sleep between polls when queue is empty |
| `QUEUE_STALE_TIMEOUT` | 300s | Heartbeat expiry threshold |
| `QUEUE_RETRY_BASE_DELAY` | 5s | Base for exponential backoff |

---

## Lifecycle

```python
worker.start()   # Spawns _run_loop + _stale_sweep_loop as asyncio.Tasks
worker.stop()    # Cancels all tasks
worker.notify()  # Wakes poll loop immediately (called after POST /queue)
```

---

## Main Poll Loop: `_run_loop()`

```
while True:
    1. await semaphore.acquire()        ← blocks if all slots busy
    2. claim_next(db)                   ← SELECT ... FOR UPDATE SKIP LOCKED
    3. if None:
         release semaphore
         wait(poll_interval OR notify_event)
         continue
    4. spawn Task: _process_item_wrapper(item, worker_id)
         ├── start heartbeat loop
         ├── _process_item(item)
         ├── cancel heartbeat
         └── release semaphore
```

### Claim Strategy
`claim_next()` uses `SELECT ... FOR UPDATE SKIP LOCKED` to atomically claim the highest-priority, oldest queued item without blocking other workers. Items with `next_attempt_at` in the future are skipped (retry backoff).

### Worker ID
Derived from semaphore state: `max_workers - semaphore._value - 1`. Used for logging and SSE events.

---

## Item Processing: `_process_item(item, worker_id)`

```
1. Create Source (type=aem, url=item.url)
2. Create IngestionJob (status=scouting)
3. pipeline.run_scout(job_id, url)
   └── auto-advances to run_process()
4. Inspect job final status:
   ├── completed → mark_completed(item_id, job_id)
   └── failed → mark_failed(item_id, error)
        ├── retries left → requeue (exponential backoff)
        └── max retries → permanent fail
```

### Important: Pipeline Never Raises
`run_scout` and `run_process` catch all exceptions internally and call `_fail_job()`. The queue worker must inspect the job's final status after the pipeline returns — it cannot rely on exceptions.

---

## Heartbeat: `_heartbeat_loop(item_id)`

Every 30 seconds, updates `last_heartbeat` on the queue item. This proves the worker is still alive and processing. If the heartbeat stops (crash, OOM, etc.), the stale sweep will reclaim the item.

```python
while True:
    await asyncio.sleep(30)
    queue_queries.update_heartbeat(db, item_id)
```

---

## Stale Sweep: `_stale_sweep_loop()`

Runs every `stale_timeout / 2` seconds (default: 150s).

```
1. Find items WHERE status='processing'
   AND last_heartbeat < now() - stale_timeout
2. Reset status → 'queued' (reclaim)
3. Publish SSE: item_reclaimed event
4. Wake poll loop via notify_event
```

This handles scenarios where a worker crashes mid-processing. The item is automatically returned to the queue for retry.

---

## Retry Logic

When `mark_failed()` is called:

```python
if item.retry_count < item.max_retries:
    item.retry_count += 1
    item.next_attempt_at = now + base_delay * (2 ** retry_count)
    item.status = 'queued'
    → outcome = "requeued"
else:
    item.status = 'failed'
    → outcome = "failed"
```

### Backoff Schedule (base_delay=5s, max_retries=3)

| Retry | Delay | Total Wait |
|---|---|---|
| 1st | 10s | 10s |
| 2nd | 20s | 30s |
| 3rd | 40s | 70s |
| Permanent fail | — | — |

---

## SSE Events Published

| Topic | Event | When |
|---|---|---|
| `worker` | `worker_started` | Item processing begins |
| `worker` | `worker_idle` | Item processing ends (always, via finally) |
| `queue` | `item_completed` | Item successfully processed |
| `queue` | `item_failed` | Item permanently failed |
| `queue` | `item_requeued` | Item failed but will retry |
| `queue` | `item_reclaimed` | Stale item reclaimed |
| `progress` | `phase_changed` | Job phase transition |

---

## Concurrency Model

```
Semaphore(MAX_CONCURRENT_JOBS=3)

  Slot 0: [processing item A] ──────────────────────►
  Slot 1: [processing item B] ────────►
  Slot 2: [processing item C] ──────────────►
           ↑                          ↑
           acquire()                  release() → claim next
```

Each slot runs independently as an asyncio.Task. The semaphore ensures no more than `MAX_CONCURRENT_JOBS` items are processed simultaneously. When a slot frees up, the poll loop immediately tries to claim the next item.
