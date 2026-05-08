import { apiClient } from "./client";
import type {
  Stats,
  SourceDetail,
  SourceSummary,
  SourceListResponse,
  FileSummary,
  FileDetail,
  Paginated,
  ActivityResponse,
  IngestRequest,
  IngestResponse,
  ConfirmSourceResponse,
  QueueItem,
  JobSummary,
  JobStatus,
  JobPage,
  ReingestRequest,
  ReingestResponse,
  GlobalSearchResponse,
  KbSyncResponse,
} from "@/types/api";

// ----- Stats -----
export const getStats = () => apiClient.get<Stats>("/stats").then((r) => r.data);

// ----- Sources -----
export interface ListSourcesParams {
  page?: number;
  size?: number;
  type?: string;
  region?: string;
  brand?: string;
  kb_target?: string;
  parent_only?: boolean;
  status?: string;
  search?: string;
  origin?: "manual" | "discovered";
  include_counts?: boolean;
}

export const listSources = (params: ListSourcesParams = {}) =>
  apiClient
    .get<SourceListResponse>("/sources", { params })
    .then((r) => r.data);

export const getSource = (id: string) =>
  apiClient.get<SourceDetail>(`/sources/${id}`).then((r) => r.data);

export const listPendingReviewSources = () =>
  apiClient
    .get<Paginated<SourceSummary>>("/sources/pending-review")
    .then((r) => r.data);

// ----- Jobs -----
export interface ListJobsParams {
  page?: number;
  size?: number;
  status?: JobStatus | JobStatus[];
  source_id?: string;
  brand?: string;
  sort?: string;
}

export const listJobs = (params: ListJobsParams = {}) => {
  const normalized: Record<string, string | number | undefined> = {
    page: params.page,
    size: params.size,
    source_id: params.source_id,
    brand: params.brand,
    sort: params.sort,
    status: Array.isArray(params.status) ? params.status.join(",") : params.status,
  };
  return apiClient
    .get<Paginated<JobSummary>>("/jobs", { params: normalized })
    .then((r) => r.data);
};

export const confirmSource = (
  id: string,
  body: { action: "process" | "discard"; reviewed_by: string }
) =>
  apiClient
    .post<ConfirmSourceResponse>(`/sources/${id}/confirm`, body)
    .then((r) => r.data);

export const deleteSource = (id: string) =>
  apiClient.delete(`/sources/${id}`).then((r) => r.data);

export const reingestSource = (id: string, body: ReingestRequest = {}) =>
  apiClient
    .post<ReingestResponse>(`/sources/${id}/reingest`, body)
    .then((r) => r.data);

export const getJobPages = (
  jobId: string,
  params: { page?: number; size?: number; outcome?: string } = {},
) =>
  apiClient
    .get<Paginated<JobPage>>(`/jobs/${jobId}/pages`, { params })
    .then((r) => r.data);

// ----- Files -----
export interface ListFilesParams {
  page?: number;
  size?: number;
  status?: string;
  region?: string;
  brand?: string;
  kb_target?: string;
  job_id?: string;
  source_id?: string;
  search?: string;
}

export const listFiles = (params: ListFilesParams = {}) =>
  apiClient
    .get<Paginated<FileSummary>>("/files", { params })
    .then((r) => r.data);

export const getFile = (id: string) =>
  apiClient.get<FileDetail>(`/files/${id}`).then((r) => r.data);

export const approveFile = (
  id: string,
  body: { reviewed_by: string; notes?: string }
) => apiClient.post<FileDetail>(`/files/${id}/approve`, body).then((r) => r.data);

export const rejectFile = (
  id: string,
  body: { reviewed_by: string; notes: string }
) => apiClient.post<FileDetail>(`/files/${id}/reject`, body).then((r) => r.data);

export const editFile = (
  id: string,
  body: { md_content: string; reviewed_by: string }
) => apiClient.put<FileDetail>(`/files/${id}`, body).then((r) => r.data);

export const revalidateFile = (id: string) =>
  apiClient.post<FileDetail>(`/files/${id}/revalidate`).then((r) => r.data);

export const deleteFile = (id: string) =>
  apiClient.delete(`/files/${id}`).then((r) => r.data);

// ----- Activity -----
export const getActivity = (limit = 20, offset = 0) =>
  apiClient
    .get<ActivityResponse>("/activity", { params: { limit, offset } })
    .then((r) => r.data);

// ----- Ingest -----
export const startIngest = (body: IngestRequest) =>
  apiClient.post<IngestResponse>("/ingest", body).then((r) => r.data);

// ----- Queue (read-only; submission flows through /ingest or reingest) -----
export const getQueueItems = (params?: { page?: number; size?: number }) =>
  apiClient.get<Paginated<QueueItem>>("/queue", { params }).then((r) => r.data);

// ----- Global Search -----
export const globalSearch = (q: string) =>
  apiClient
    .get<GlobalSearchResponse>("/search", { params: { q } })
    .then((r) => r.data);

// ----- KB (Bedrock) -----
// /kb/search and /kb/chat are SSE — see src/api/kbStream.ts
export const kbSync = () =>
  apiClient.post<KbSyncResponse>("/kb/sync").then((r) => r.data);
