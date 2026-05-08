// Backend type mirror — keep in sync with kb_manager/schemas/*

export type KbTarget = "public" | "internal";
// DB-stored brand values. Note: "abg" (group selector) is mapped to "avis_budget" at the API
// boundary by BrandContext.brandParam(); records returned from the backend use these values.
export type Brand = "avis_budget" | "avis" | "budget" | null;

export type SourceStatus =
  | "active"
  | "needs_confirmation"
  | "dismissed"
  | "ingested"
  | "failed";

export type FileStatus =
  | "pending_review"
  | "approved"
  | "rejected"
  | "superseded";

export type JobStatus =
  | "scouting"
  | "awaiting_confirmation"
  | "processing"
  | "completed"
  | "failed";

export interface JobSummary {
  id: string;
  source_id: string;
  source_label: string;
  source_type: string;
  status: JobStatus;
  started_at: string | null;
  completed_at: string | null;
  progress_pct: number;
  discovered_count: number;
  error_message: string | null;
}

export type Verdict = "pass" | "fail" | "warn" | string;

export interface Stats {
  total_files: number;
  pending_review: number;
  approved: number;
  rejected: number;
  active_jobs: number;
  sources_count: number;
  kb_public_files: number;
  kb_internal_files: number;
  failed_jobs_count: number;
  discovered_today: number;
}

export type DisplayStatus =
  | "idle"
  | "queued"
  | "discovering"
  | "extracting"
  | "qa"
  | "failed"
  | "needs_review";

export interface SourceSummary {
  id: string;
  url: string;
  type: string;
  kb_target: KbTarget;
  status: SourceStatus;
  display_status: DisplayStatus;
  region: string | null;
  brand: string | null;
  origin: "manual" | "discovered";
  run_count: number;
  last_run_at: string | null;
  active_job_id?: string | null;
  child_count?: number;
  created_at?: string;
  updated_at?: string;
}

export interface SourceListCounts {
  by_status: Partial<Record<DisplayStatus, number>>;
  by_region: Record<string, number>;
  by_brand: Record<string, number>;
  by_origin: Partial<Record<"manual" | "discovered", number>>;
  // Backend gap (phase 2): by_type and by_kb_target not yet exposed.
  by_type?: Record<string, number>;
  by_kb_target?: Partial<Record<KbTarget, number>>;
}

export interface SourceListResponse extends Paginated<SourceSummary> {
  counts: SourceListCounts | null;
}

export interface FileStats {
  total: number;
  approved: number;
  pending: number;
  rejected: number;
}

export interface SourceRuntime {
  queue_position: number | null;
  worker_id: number | null;
}

export interface ActiveFile {
  id: string;
  title: string;
  status: FileStatus;
}

export interface RunHistoryEntry {
  id: string;
  status: JobStatus;
  started_at: string | null;
  completed_at: string | null;
}

export interface SourceDetail extends SourceSummary {
  scout_summary: Record<string, unknown> | null;
  file_stats: FileStats;
  children?: SourceSummary[];
  steering_prompt: string | null;
  parent_url: string | null;
  active_files: ActiveFile[];
  run_history: RunHistoryEntry[];
  metadata?: Record<string, unknown> | null;
  runtime: SourceRuntime | null;
  last_ingested_at?: string | null;
}

// POST /sources/{id}/reingest
export interface ReingestRequest {
  steering_prompt?: string | null;
  priority?: number;
}

export interface ReingestResponse {
  job_id: string;
  source_id: string;
  status: JobStatus;
}

// GET /jobs/{job_id}/pages
export type PageOutcome = "created" | "replaced" | "skipped";

export interface JobPage {
  id: string;
  job_id: string;
  url: string;
  outcome: PageOutcome;
  reason: string | null;
  bytes: number | null;
  file_id: string | null;
  created_at: string;
}

export interface FileSummary {
  id: string;
  title: string;
  source_url: string | null;
  kb_target: KbTarget;
  region: string | null;
  brand: string | null;
  category: string | null;
  visibility: string | null;
  tags: string[];
  status: FileStatus;
  quality_verdict: Verdict | null;
  uniqueness_verdict: Verdict | null;
  created_at: string;
  updated_at: string;
  reviewed_at?: string | null;
  reviewed_by?: string | null;
}

export interface SimilarFile {
  id: string;
  title: string;
  similarity?: number;
}

export interface SourceRef {
  id: string;
  url: string;
}

export interface FileDetail extends FileSummary {
  md_content: string;
  quality_reasoning: string | null;
  uniqueness_reasoning: string | null;
  similar_files: SimilarFile[];
  sources: SourceRef[];
  review_notes: string | null;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export interface ActivityItem {
  id: string;
  type: "file_approved" | "file_rejected" | "job_completed" | "job_failed" | "source_confirmed" | "source_discarded" | string;
  actor: string | null;
  target_id: string;
  target_title: string;
  action: string;
  timestamp: string;
}

export interface ActivityResponse {
  items: ActivityItem[];
  total: number;
}

// Ingest
export interface AemUrlInput {
  url: string;
  region: string;
  brand?: string | null;
  nav_label?: string | null;
  nav_section?: string | null;
  page_path?: string | null;
}

export interface IngestRequest {
  connector_type: "aem";
  // Backend rejects empty arrays (min_length=1). Callers must guard.
  urls: AemUrlInput[];
  kb_target: KbTarget;
  steering_prompt?: string | null;
}

export interface JobCreated {
  job_id: string;
  source_id: string;
  source_url: string;
  status: JobStatus;
}

export interface IngestResponse {
  jobs: JobCreated[];
}

// POST /sources/{id}/confirm response
export interface ConfirmSourceResponse {
  source_id: string;
  job_id: string | null;
  status: SourceStatus | JobStatus;
}

// Queue System v2 types — mirrors backend v2 API shapes

/** Structured event envelope from /api/v1/events/stream */
export interface SSEEnvelope {
  timestamp: number;
  topic: string;
  event: string;
  data: Record<string, unknown>;
}

export interface QueueItem {
  id: string;
  source_id: string;
  status: string;
  retry_count: number;
  max_retries: number;
  priority: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export type WorkerEventName = "worker_started" | "worker_idle";

export type ProgressEventName =
  | "phase_changed"
  | "scouting_started"
  | "component_found"
  | "link_found"
  | "link_classified"
  | "scout_complete"
  | "extraction_started"
  | "file_created"
  | "qa_complete"
  | "job_complete"
  | "error";

export interface WorkerState {
  workerId: number;
  status: "idle" | "active";
  url: string | null;
  phase: string | null;
  startedAt: number | null;
}

// Global search
export interface SearchFileHit {
  id: string;
  title: string;
  status: FileStatus;
  tags: string[];
  category: string | null;
  source_url: string | null;
}

export interface SearchSourceHit {
  id: string;
  url: string;
  brand: string | null;
  region: string | null;
}

export interface SearchJobHit {
  id: string;
  source_label: string;
  status: JobStatus;
  brand: string | null;
}

export interface GlobalSearchResponse {
  q: string;
  files: { items: SearchFileHit[]; total: number };
  sources: { items: SearchSourceHit[]; total: number };
  jobs: { items: SearchJobHit[]; total: number };
}

// KB (Bedrock) — POST /kb/search, /kb/chat, /kb/sync
export interface KbSearchRequest {
  query: string;
  kb_target: KbTarget;
  limit?: number;
}

export interface KbSearchResult {
  rank: number;
  title: string;
  snippet: string;
  source_url: string | null;
  score: number;
  s3_uri: string | null;
}

export interface KbChatRequest {
  query: string;
  kb_target: KbTarget;
  context_limit?: number;
}

export interface KbChatSource {
  title: string;
  url: string | null;
  snippet: string;
  s3_uri: string | null;
}

export interface KbSyncResponse {
  ingestion_job_id: string;
  status: string;
}
