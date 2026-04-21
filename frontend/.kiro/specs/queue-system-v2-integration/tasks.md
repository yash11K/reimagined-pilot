# Implementation Plan: Queue System v2 Integration

## Overview

Incrementally integrate Backend Queue System v2 into the ABG Knowledge System frontend. The plan starts with foundational types and API functions, builds the new SSE hook, then layers on worker status, queue management, pipeline strip upgrade, and page layout changes — each step wiring into the previous one.

## Tasks

- [x] 1. Add v2 TypeScript types to the types module
  - [x] 1.1 Define SSE envelope, queue, and worker types in `src/types/api.ts`
    - Add `SSEEnvelope` type with `timestamp`, `topic`, `event`, `data` fields
    - Add `QueueItem` type with `id`, `url`, `status`, `retry_count`, `max_retries`, `priority`, `error_message`, `created_at`, `updated_at`
    - Add `QueueSubmitRequest` (`urls: string[]`, `priority: number`) and `QueueSubmitResponse` (`queued`, `skipped`, `item_ids`)
    - Add `WorkerEventName` and `ProgressEventName` union types
    - Add client-side `WorkerState` interface
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 2. Add queue API endpoint functions
  - [x] 2.1 Add `submitToQueue` and `getQueueItems` to `src/api/endpoints.ts`
    - `submitToQueue` sends POST to `/queue` with `QueueSubmitRequest`, returns `QueueSubmitResponse`
    - `getQueueItems` sends GET to `/queue` with optional `page`/`size` params, returns `Paginated<QueueItem>`
    - Both use the existing `apiClient` instance
    - _Requirements: 7.1, 7.2, 7.3_

- [x] 3. Implement the `useSSEv2` hook
  - [x] 3.1 Create `src/hooks/useSSEv2.ts`
    - Open a single `EventSource` to `/api/v1/events/stream` via `sseUrl`
    - Parse every `message` event as JSON into `SSEv2Event` shape (with `_clientId` and `_receivedAt` client fields)
    - Filter incoming events by the `topics` option array; pass all if empty/undefined
    - Silently drop events with unrecognized structure (forward-compatible)
    - Maintain a configurable ring buffer (default 50), newest-first
    - Expose `events` array and `status` (`idle` | `open` | `error` | `closed`)
    - Rely on native `EventSource` reconnection on error
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_
  - [ ]* 3.2 Write unit tests for `useSSEv2`
    - Test JSON parsing of envelope payloads
    - Test topic filtering (only matching topics retained)
    - Test ring buffer capacity enforcement
    - Test status transitions (idle → open → error)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 4. Checkpoint — Verify foundation layers
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement the `useWorkerStatus` hook
  - [x] 5.1 Create `src/hooks/useWorkerStatus.ts`
    - Internally call `useSSEv2({ topics: ["worker", "progress"] })`
    - Use `useReducer` with actions: `WORKER_STARTED`, `PHASE_CHANGED`, `WORKER_IDLE`
    - `worker_started` → set worker active with URL, initial phase, and `startedAt` timestamp
    - `phase_changed` → update phase for the matching worker
    - `worker_idle` → reset worker to idle, clear URL/phase/startedAt
    - Accept optional `workerCount` param (default 3), return `WorkerState[]`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - [ ]* 5.2 Write unit tests for `useWorkerStatus`
    - Test reducer transitions for started → phase change → idle
    - Test that unrelated worker events don't affect other workers
    - _Requirements: 4.2, 4.3, 4.4_

- [x] 6. Build the `WorkerCards` component
  - [x] 6.1 Create `src/components/discovery/WorkerCards.tsx`
    - Call `useWorkerStatus()` to get worker state array
    - Render a horizontal row of cards using existing `Card`, `CardHeader`, `CardBody`
    - Each card: heading "Worker N", status indicator (green pulsing dot active / gray idle), truncated URL, phase label
    - Active cards show a continuously updating elapsed timer (1s `setInterval` from `startedAt`)
    - Idle cards display "Idle" with muted styling
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

- [x] 7. Build the `QueueSubmitForm` component
  - [x] 7.1 Create `src/components/discovery/QueueSubmitForm.tsx`
    - Collapsible section with textarea (one URL per line), numeric priority input (default 0, tooltip), and "Add to Queue" button
    - Use `useMutation` calling `submitToQueue`; invalidate `["queue"]` on success
    - On success: show toast with queued/skipped counts; use warning tone when `skipped > 0`
    - On error: show error toast with failure reason
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 8. Build the `QueueTable` component
  - [x] 8.1 Create `src/components/discovery/QueueTable.tsx`
    - Fetch via `useQuery` calling `getQueueItems` with `refetchInterval: 15_000`
    - Subscribe to `useSSEv2({ topics: ["queue"] })` and trigger `queryClient.invalidateQueries(["queue"])` on any queue event, throttled to 2s
    - Columns: URL, Status, Retries, Priority, Error, Last Updated
    - Compute display status: failed + retry_count===max_retries → "exhausted" (err badge); failed + retry_count<max_retries → "requeued" (warn badge); queued → neutral; processing → info; completed → ok
    - Show "retry N/M" badge when `retry_count > 0`
    - Show priority badge when `priority > 0`
    - Use existing `DataTable`, `Table`, `Badge`, `Pagination` components
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_
  - [ ]* 8.2 Write unit tests for queue status display logic
    - Test exhausted vs requeued derivation
    - Test retry badge formatting
    - Test priority badge visibility
    - _Requirements: 3.2, 3.3, 3.4, 3.5_

- [x] 9. Checkpoint — Verify new components render correctly
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Upgrade `LivePipelineStrip` to use `useSSEv2`
  - [x] 10.1 Modify `src/components/discovery/LivePipelineStrip.tsx`
    - Replace `useSSE("/logs/stream")` with `useSSEv2({ topics: ["progress"] })`
    - Update event rendering to use `SSEv2Event` shape (topic, event name, data)
    - Add a topic badge next to each event entry
    - Render `error` events with error-tone styling
    - Retain throttled React Query invalidation for `sources` and `stats` (2s throttle)
    - Update `formatLine` to derive human-readable summaries from structured `data` field
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 11. Reorganize the `DiscoveryTools` page layout
  - [x] 11.1 Update `src/pages/DiscoveryTools.tsx`
    - Import and render `WorkerCards` row directly below the KPI cards section
    - Replace the Discovery Jobs table with `QueueSubmitForm` (collapsible, above table) + `QueueTable` in the 2-col main area
    - Keep Uncertain Links panel in its 1-col side position
    - Keep `LivePipelineStrip` at the bottom, full width
    - Remove old `useSSE`-based imports if no longer needed
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 12. Final checkpoint — Full integration verification
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirement clauses for traceability
- The design uses TypeScript throughout; all code examples and implementations use TypeScript + React
- Checkpoints ensure incremental validation at foundation, component, and integration levels
- The existing `useSSE` hook in `src/hooks/useSSE.ts` can be removed once `LivePipelineStrip` is migrated (task 10) and no other consumers remain
