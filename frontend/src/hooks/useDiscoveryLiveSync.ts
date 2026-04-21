import { useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSSEv2, type SSEv2Event } from "./useSSEv2";
import type { JobSummary, JobStatus, Paginated } from "@/types/api";

const INVALIDATE_THROTTLE_MS = 2_000;

function patchJobProgress(
  list: Paginated<JobSummary> | undefined,
  jobId: string,
  patch: Partial<JobSummary>
): Paginated<JobSummary> | undefined {
  if (!list) return list;
  let hit = false;
  const items = list.items.map((j) => {
    if (j.id !== jobId) return j;
    hit = true;
    return { ...j, ...patch };
  });
  return hit ? { ...list, items } : list;
}

/**
 * Subscribes to queue/progress SSE topics.
 * - `queue` events: throttled list invalidations (stats, sources, jobs).
 * - `progress` events: patch the matching job row in place (progress_pct + status).
 */
export function useDiscoveryLiveSync() {
  const qc = useQueryClient();
  const lastInvalidate = useRef(0);

  const onEvent = (ev: SSEv2Event) => {
    if (ev.topic === "progress") {
      const d = ev.data as {
        job_id?: string;
        progress_pct?: number;
        status?: JobStatus;
      };
      if (!d.job_id) return;
      const patch: Partial<JobSummary> = {};
      if (typeof d.progress_pct === "number") patch.progress_pct = d.progress_pct;
      if (d.status) patch.status = d.status;
      if (Object.keys(patch).length === 0) return;

      qc.setQueriesData<Paginated<JobSummary>>(
        { queryKey: ["jobs"] },
        (old) => patchJobProgress(old, d.job_id!, patch)
      );
      return;
    }

    if (ev.topic === "queue") {
      const now = Date.now();
      if (now - lastInvalidate.current < INVALIDATE_THROTTLE_MS) return;
      lastInvalidate.current = now;
      qc.invalidateQueries({ queryKey: ["stats"] });
      qc.invalidateQueries({ queryKey: ["sources"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    }
  };

  useSSEv2({ topics: ["queue", "progress"], onEvent });
}
