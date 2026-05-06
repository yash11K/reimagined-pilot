import { useState, useCallback } from "react";
import { useSSE, type SSEEvent } from "./useSSE";

export interface ScoutEvent {
  event: string;
  data: Record<string, unknown>;
  at: number;
}

/**
 * Subscribes to `/ingest/{jobId}/scout-stream` for real-time scout progress
 * after a source is confirmed. Call `attach(jobId)` to start listening,
 * `detach()` to stop.
 *
 * Returns the stream of scout events and a `complete` flag.
 */
export function useJobScoutStream() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [scoutEvents, setScoutEvents] = useState<ScoutEvent[]>([]);
  const [complete, setComplete] = useState(false);

  const path = jobId ? `/ingest/${jobId}/scout-stream` : null;

  const onNamedEvent = useCallback((name: string, ev: SSEEvent<unknown>) => {
    const entry: ScoutEvent = {
      event: name,
      data: (ev.data ?? {}) as Record<string, unknown>,
      at: ev.at,
    };
    setScoutEvents((prev) => [...prev, entry]);

    if (name === "scout_complete" || name === "job_complete") {
      setComplete(true);
    }
  }, []);

  const onMessage = useCallback((ev: SSEEvent<unknown>) => {
    const entry: ScoutEvent = {
      event: ev.event,
      data: (ev.data ?? {}) as Record<string, unknown>,
      at: ev.at,
    };
    setScoutEvents((prev) => [...prev, entry]);
  }, []);

  useSSE(path, {
    enabled: !!jobId && !complete,
    onNamedEvent,
    onMessage,
    bufferSize: 100,
  });

  const attach = useCallback((id: string) => {
    setJobId(id);
    setScoutEvents([]);
    setComplete(false);
  }, []);

  const detach = useCallback(() => {
    setJobId(null);
    setScoutEvents([]);
    setComplete(false);
  }, []);

  return { jobId, scoutEvents, complete, attach, detach };
}
