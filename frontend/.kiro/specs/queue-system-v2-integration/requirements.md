# Requirements Document

## Introduction

Integrate the Backend Queue System v2 into the existing ABG Knowledge System frontend. The backend has migrated from a flat log-stream SSE endpoint (`/api/v1/logs/stream`) to a structured, topic-based event stream (`/api/v1/events/stream`), introduced a queue submission API with priority and deduplication, enriched queue item metadata (retries, priority, error messages), and added worker lifecycle events. This feature covers rewriting the SSE layer, building new queue management UI, adding worker status cards, and updating the Discovery Tools page to surface all v2 capabilities.

## Glossary

- **Event_Stream**: The SSE connection at `GET /api/v1/events/stream` that delivers all real-time backend events in a unified `{timestamp, topic, event, data}` envelope
- **Topic**: A category string on each SSE event (`worker`, `queue`, `progress`) used for client-side filtering
- **Queue_Item**: A URL-based work unit submitted to the backend queue, carrying status, retry metadata, priority, and error information
- **Worker_Card**: A UI card representing one of N concurrent backend workers (currently 3), showing its active/idle state, current URL, pipeline phase, and elapsed time
- **Pipeline_Phase**: A named stage in the per-item processing pipeline (e.g. scouting_started, component_found, extraction_started, qa_complete)
- **Priority**: An integer field on a Queue_Item where higher values cause the backend to process the item first
- **Requeue**: The backend action of returning a failed Queue_Item to the queue with incremented retry_count and exponential backoff, distinct from terminal failure
- **SSE_Hook**: The React hook (`useSSE`) responsible for opening an EventSource connection, parsing events, and distributing them to subscribers
- **Queue_Submission_Form**: The UI form on the Discovery Tools page for submitting URLs to the backend queue with optional priority
- **Discovery_Page**: The existing `DiscoveryTools.tsx` page that hosts source tables, uncertain links, and the live pipeline strip

## Requirements

### Requirement 1: Migrate SSE Connection to v2 Event Stream

**User Story:** As a frontend developer, I want the SSE hook to connect to the new `/events/stream` endpoint and parse the unified event envelope, so that all components receive structured, topic-based events.

#### Acceptance Criteria

1. WHEN the SSE_Hook is initialized with a path, THE SSE_Hook SHALL open an EventSource connection to `/api/v1/events/stream` instead of `/api/v1/logs/stream`
2. WHEN an SSE message is received, THE SSE_Hook SHALL parse the JSON payload into the shape `{timestamp: number, topic: string, event: string, data: object}`
3. WHEN a parsed event contains an unrecognized topic or event name, THE SSE_Hook SHALL ignore the event without throwing an error (forward-compatible)
4. THE SSE_Hook SHALL expose a subscription mechanism that allows consumers to filter events by topic (worker, queue, progress)
5. WHEN the EventSource connection encounters an error, THE SSE_Hook SHALL set its status to "error" and allow the browser's native EventSource reconnection to retry
6. THE SSE_Hook SHALL maintain a configurable ring buffer of recent events (default 50) ordered newest-first

### Requirement 2: Queue Submission with Priority and Deduplication Feedback

**User Story:** As an operator, I want to submit URLs to the processing queue with an optional priority level and see which URLs were skipped as duplicates, so that I can manage ingestion efficiently.

#### Acceptance Criteria

1. THE Queue_Submission_Form SHALL include a text area for entering one or more URLs (one per line) and a submit button labeled "Add to Queue"
2. WHERE the priority feature is used, THE Queue_Submission_Form SHALL include a numeric input field labeled "Priority" with a default value of 0 and a tooltip explaining that higher values are processed first
3. WHEN the user submits the form, THE Queue_Submission_Form SHALL send a POST request to `/api/v1/queue` with the URLs array and priority value
4. WHEN the POST response is received, THE Queue_Submission_Form SHALL display a toast notification showing the count of queued items and the count of skipped (duplicate) items
5. IF the POST request fails, THEN THE Queue_Submission_Form SHALL display an error toast with the failure reason
6. WHEN the POST response contains `skipped > 0`, THE Queue_Submission_Form SHALL include the skipped count in the toast message using a warning tone

### Requirement 3: Queue Table with Retry and Priority Display

**User Story:** As an operator, I want to see the full queue with status, retry progress, priority, and error details for each item, so that I can monitor processing health at a glance.

#### Acceptance Criteria

1. THE Discovery_Page SHALL display a Queue Items table showing columns: URL, Status, Retries, Priority, Error, and Last Updated
2. WHEN a Queue_Item has `retry_count > 0`, THE Queue Items table SHALL display a badge showing "retry N/M" where N is retry_count and M is max_retries
3. WHEN a Queue_Item has `priority > 0`, THE Queue Items table SHALL display the priority value in a branded badge
4. WHEN a Queue_Item has `status = "failed"` and `retry_count = max_retries`, THE Queue Items table SHALL display the status as "exhausted" with an error-tone badge
5. WHEN a Queue_Item has `status = "failed"` and `retry_count < max_retries`, THE Queue Items table SHALL display the status as "requeued" with a warning-tone badge
6. THE Discovery_Page SHALL fetch queue items from `GET /api/v1/queue` and refresh the data every 15 seconds
7. WHEN a `queue` topic event is received via the Event_Stream, THE Queue Items table SHALL trigger a data refresh within 2 seconds

### Requirement 4: Worker Status Cards

**User Story:** As an operator, I want to see real-time status cards for each backend worker showing what they are processing, their current phase, and elapsed time, so that I can monitor system throughput.

#### Acceptance Criteria

1. THE Discovery_Page SHALL display exactly N Worker_Cards in a horizontal row, where N equals the MAX_CONCURRENT_JOBS value (currently 3)
2. WHEN a `worker_started` event is received for a worker, THE corresponding Worker_Card SHALL transition to an active state displaying the URL being processed and the initial pipeline phase
3. WHEN a `phase_changed` event is received for a worker, THE corresponding Worker_Card SHALL update its displayed phase label to the new phase name
4. WHEN a `worker_idle` event is received for a worker, THE corresponding Worker_Card SHALL transition to an idle state, clearing the URL and phase, and displaying "Idle"
5. WHILE a Worker_Card is in the active state, THE Worker_Card SHALL display a continuously updating elapsed timer computed client-side from the `worker_started` event timestamp
6. THE Worker_Card SHALL display the worker identifier (Worker 0, Worker 1, Worker 2) as its heading
7. WHILE a Worker_Card is in the active state, THE Worker_Card SHALL display a green pulsing indicator; WHILE idle, THE Worker_Card SHALL display a gray muted indicator

### Requirement 5: Live Pipeline Event Feed Upgrade

**User Story:** As an operator, I want the live pipeline strip to show structured progress events from the v2 stream with topic labels and human-readable descriptions, so that I can follow processing in real time.

#### Acceptance Criteria

1. THE LivePipelineStrip SHALL subscribe to the `progress` topic from the Event_Stream instead of listening to raw `/logs/stream` messages
2. WHEN a progress event is received, THE LivePipelineStrip SHALL display the event name, a human-readable summary derived from the event data, and a relative timestamp
3. THE LivePipelineStrip SHALL display a topic badge (e.g. "progress", "queue") next to each event entry for visual categorization
4. WHEN an `error` event is received on the progress topic, THE LivePipelineStrip SHALL render the entry with an error-tone style
5. THE LivePipelineStrip SHALL continue to trigger React Query cache invalidations for `sources` and `stats` queries on relevant events, throttled to at most once per 2 seconds

### Requirement 6: Queue and Worker TypeScript Types

**User Story:** As a frontend developer, I want well-defined TypeScript types for all v2 API shapes, so that the codebase remains type-safe and maintainable.

#### Acceptance Criteria

1. THE types module SHALL export an `SSEEnvelope` type with fields: `timestamp: number`, `topic: string`, `event: string`, `data: Record<string, unknown>`
2. THE types module SHALL export a `QueueItem` type with fields: `id: string`, `url: string`, `status: string`, `retry_count: number`, `max_retries: number`, `priority: number`, `error_message: string | null`, and timestamp fields
3. THE types module SHALL export a `QueueSubmitResponse` type with fields: `queued: number`, `skipped: number`, `item_ids: string[]`
4. THE types module SHALL export a `QueueSubmitRequest` type with fields: `urls: string[]`, `priority: number`
5. THE types module SHALL export union types for worker event names (`worker_started`, `worker_idle`) and progress event names (`phase_changed`, `scouting_started`, `component_found`, `link_found`, `link_classified`, `scout_complete`, `extraction_started`, `file_created`, `qa_complete`, `job_complete`, `error`)

### Requirement 7: API Endpoint Functions for Queue Operations

**User Story:** As a frontend developer, I want dedicated API functions for queue operations, so that components can call them consistently through the existing API client layer.

#### Acceptance Criteria

1. THE endpoints module SHALL export a `submitToQueue` function that sends a POST request to `/queue` with a `QueueSubmitRequest` body and returns a `QueueSubmitResponse`
2. THE endpoints module SHALL export a `getQueueItems` function that sends a GET request to `/queue` and returns a paginated list of `QueueItem` objects
3. THE endpoints module SHALL use the existing `apiClient` instance for all queue requests, inheriting base URL and error interceptor configuration

### Requirement 8: Discovery Page Layout Reorganization

**User Story:** As an operator, I want the Discovery Tools page to present queue management, worker status, and live events in a clear visual hierarchy, so that I can operate the system efficiently from a single page.

#### Acceptance Criteria

1. THE Discovery_Page SHALL display the Worker_Cards row directly below the KPI cards section
2. THE Discovery_Page SHALL display the Queue_Submission_Form as a collapsible section or inline form above the Queue Items table
3. THE Discovery_Page SHALL display the Queue Items table in the main content area below the Worker_Cards, replacing or augmenting the existing Discovery Jobs table
4. THE Discovery_Page SHALL display the LivePipelineStrip at the bottom of the page, below all tables
5. THE Discovery_Page SHALL retain the existing Uncertain Links side panel in its current position within the grid layout
