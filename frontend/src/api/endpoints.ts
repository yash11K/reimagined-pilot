import { apiClient } from "./client";
import type {
  Stats,
  SourceSummary,
  SourceDetail,
  FileSummary,
  FileDetail,
  Paginated,
  ActivityResponse,
  IngestRequest,
  IngestResponse,
  NavTreeNode,
  QueueSubmitRequest,
  QueueSubmitResponse,
  QueueItem,
  JobSummary,
  JobStatus,
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
}

export const listSources = (params: ListSourcesParams = {}) =>
  apiClient
    .get<Paginated<SourceSummary>>("/sources", { params })
    .then((r) => r.data);

export const getSource = (id: string) =>
  apiClient.get<SourceDetail>(`/sources/${id}`).then((r) => r.data);

export const getActiveJobs = () =>
  apiClient
    .get<{ active_jobs: Record<string, string> }>("/sources/active-jobs")
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
) => apiClient.post(`/sources/${id}/confirm`, body).then((r) => r.data);

export const deleteSource = (id: string) =>
  apiClient.delete(`/sources/${id}`).then((r) => r.data);

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

// ----- Nav tree -----
export const getNavTree = (url: string, force_refresh = false) =>
  apiClient
    .get<NavTreeNode[]>("/nav/tree", { params: { url, force_refresh } })
    .then((r) => r.data);

// ----- Queue -----
export const submitToQueue = (body: QueueSubmitRequest) =>
  apiClient.post<QueueSubmitResponse>("/queue", body).then((r) => r.data);

export const getQueueItems = (params?: { page?: number; size?: number }) =>
  apiClient.get<Paginated<QueueItem>>("/queue", { params }).then((r) => r.data);
