// Backend type mirror — keep in sync with kb_manager/schemas/*

export type KbTarget = "public" | "internal";
export type Brand = "abg" | "avis" | "budget" | null;

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

export interface SourceSummary {
  id: string;
  url: string;
  type: string;
  kb_target: KbTarget;
  status: SourceStatus;
  region: string | null;
  brand: string | null;
  is_scouted: boolean;
  is_ingested: boolean;
  job_count: number;
  child_count: number;
  created_at?: string;
  updated_at?: string;
}

export interface FileStats {
  total: number;
  approved: number;
  pending: number;
  rejected: number;
}

export interface SourceDetail extends SourceSummary {
  scout_summary: Record<string, unknown> | null;
  file_stats: FileStats;
  children?: SourceSummary[];
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
  region?: string | null;
  brand?: string | null;
  nav_label?: string | null;
  nav_section?: string | null;
  page_path?: string | null;
}

export interface IngestRequest {
  connector_type: "aem" | "upload";
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

// Nav tree (matches kb_manager/services/nav_parser.py:_link_to_node)
export interface NavTreeNode {
  label: string;
  path: string;
  url: string;
  section: string;
  model_json_url: string;
  children: NavTreeNode[];
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
  url: string;
  status: string;
  retry_count: number;
  max_retries: number;
  priority: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface QueueSubmitRequest {
  urls: string[];
  priority: number;
}

export interface QueueSubmitResponse {
  queued: number;
  skipped: number;
  item_ids: string[];
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
