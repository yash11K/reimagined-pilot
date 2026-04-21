import { useEffect, useRef, useState } from "react";
import { sseUrl } from "@/api/client";

export interface SSEEvent<T = unknown> {
  event: string;
  data: T;
  id: string;
  at: number;
}

interface UseSSEOptions<T> {
  enabled?: boolean;
  /** Called on every message event (default SSE event). */
  onMessage?: (ev: SSEEvent<T>) => void;
  /** Called on named events (e.g. "progress", "scout_complete"). */
  onNamedEvent?: (name: string, ev: SSEEvent<T>) => void;
  /** Max events to retain in history. */
  bufferSize?: number;
}

/**
 * Opens an EventSource at the given API path. Parses JSON payloads where
 * possible. Buffers a ring of recent events. Auto-closes on unmount.
 *
 * NOTE: Browsers' EventSource does not support POST bodies or custom headers.
 * Only use for GET SSE endpoints (logs/stream, scout-stream, progress-stream).
 */
export function useSSE<T = unknown>(
  path: string | null,
  opts: UseSSEOptions<T> = {}
) {
  const { enabled = true, onMessage, onNamedEvent, bufferSize = 50 } = opts;
  const [events, setEvents] = useState<SSEEvent<T>[]>([]);
  const [status, setStatus] = useState<"idle" | "open" | "closed" | "error">("idle");
  const esRef = useRef<EventSource | null>(null);
  const msgRef = useRef(onMessage);
  const namedRef = useRef(onNamedEvent);
  msgRef.current = onMessage;
  namedRef.current = onNamedEvent;

  useEffect(() => {
    if (!path || !enabled) return;
    const es = new EventSource(sseUrl(path));
    esRef.current = es;
    setStatus("open");

    const parse = (raw: string): T => {
      try {
        return JSON.parse(raw) as T;
      } catch {
        return raw as unknown as T;
      }
    };

    const push = (ev: SSEEvent<T>) => {
      setEvents((prev) => {
        const next = [ev, ...prev];
        return next.length > bufferSize ? next.slice(0, bufferSize) : next;
      });
    };

    const handleGeneric = (e: MessageEvent) => {
      const ev: SSEEvent<T> = {
        event: "message",
        data: parse(e.data),
        id: e.lastEventId || `${Date.now()}-${Math.random()}`,
        at: Date.now(),
      };
      push(ev);
      msgRef.current?.(ev);
    };

    const handleNamed = (name: string) => (e: MessageEvent) => {
      const ev: SSEEvent<T> = {
        event: name,
        data: parse(e.data),
        id: e.lastEventId || `${Date.now()}-${Math.random()}`,
        at: Date.now(),
      };
      push(ev);
      namedRef.current?.(name, ev);
    };

    es.onmessage = handleGeneric;
    es.onerror = () => setStatus("error");

    // Listen for common named events from backend
    const named = [
      "progress",
      "scout_discovered",
      "scout_classified",
      "scout_complete",
      "page_processing",
      "file_created",
      "job_complete",
      "log",
      "ping",
      "keepalive",
    ];
    const attached: Array<[string, EventListener]> = [];
    for (const name of named) {
      const fn = handleNamed(name) as unknown as EventListener;
      es.addEventListener(name, fn);
      attached.push([name, fn]);
    }

    return () => {
      for (const [name, fn] of attached) es.removeEventListener(name, fn);
      es.close();
      esRef.current = null;
      setStatus("closed");
    };
  }, [path, enabled, bufferSize]);

  return { events, status };
}
