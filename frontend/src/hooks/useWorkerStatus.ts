import { useEffect, useReducer } from "react";
import { useSSEv2 } from "./useSSEv2";
import type { WorkerState } from "@/types/api";

// --- Reducer actions ---

type WorkerAction =
  | { type: "WORKER_STARTED"; workerId: number; url: string; phase: string; startedAt: number }
  | { type: "PHASE_CHANGED"; workerId: number; phase: string }
  | { type: "WORKER_IDLE"; workerId: number };

function createIdleWorkers(count: number): WorkerState[] {
  return Array.from({ length: count }, (_, i) => ({
    workerId: i,
    status: "idle" as const,
    url: null,
    phase: null,
    startedAt: null,
  }));
}

function workerReducer(state: WorkerState[], action: WorkerAction): WorkerState[] {
  const idx = state.findIndex((w) => w.workerId === action.workerId);
  if (idx === -1) return state;

  switch (action.type) {
    case "WORKER_STARTED": {
      const updated = [...state];
      updated[idx] = {
        ...updated[idx],
        status: "active",
        url: action.url,
        phase: action.phase,
        startedAt: action.startedAt,
      };
      return updated;
    }
    case "PHASE_CHANGED": {
      const updated = [...state];
      updated[idx] = {
        ...updated[idx],
        phase: action.phase,
      };
      return updated;
    }
    case "WORKER_IDLE": {
      const updated = [...state];
      updated[idx] = {
        ...updated[idx],
        status: "idle",
        url: null,
        phase: null,
        startedAt: null,
      };
      return updated;
    }
    default:
      return state;
  }
}

// --- Hook ---

export function useWorkerStatus(workerCount: number = 3): WorkerState[] {
  const { events } = useSSEv2({ topics: ["worker", "progress"] });
  const [workers, dispatch] = useReducer(workerReducer, workerCount, createIdleWorkers);

  useEffect(() => {
    for (const ev of events) {
      const workerId = ev.data.worker_id as number | undefined;
      if (workerId == null) continue;

      switch (ev.event) {
        case "worker_started":
          dispatch({
            type: "WORKER_STARTED",
            workerId,
            url: (ev.data.url as string) ?? "",
            phase: (ev.data.phase as string) ?? "",
            startedAt: ev.timestamp,
          });
          break;
        case "phase_changed":
          dispatch({
            type: "PHASE_CHANGED",
            workerId,
            phase: (ev.data.phase as string) ?? "",
          });
          break;
        case "worker_idle":
          dispatch({ type: "WORKER_IDLE", workerId });
          break;
      }
    }
  }, [events]);

  return workers;
}
