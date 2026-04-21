import { useEffect, useRef, useState, useCallback } from "react";
import { sseUrl } from "@/api/client";

/**
 * Parsed SSE v2 event with client-side metadata.
 */
export interface SSEv2Event {
  timestamp: number;
  topic: string;
  event: string;
  data: Record<string, unknown>;
  _clientId: string;
  _receivedAt: number;
}

export interface UseSSEv2Options {
  enabled?: boolean;
  /** Filter to these topics; empty or undefined = all topics. */
  topics?: string[];
  /** Ring buffer capacity (default 50). */
  bufferSize?: number;
  /** Called on every matching event. */
  onEvent?: (ev: SSEv2Event) => void;
}

let _counter = 0;
const nextClientId = (): string => {
  try {
    return crypto.randomUUID();
  } catch {
    return `sse-${Date.now()}-${++_counter}`;
  }
};

/**
 * Validates that a parsed JSON value has the required SSE v2 envelope shape.
 */
function isValidEnvelope(
  val: unknown
): val is { timestamp: number; topic: string; event: string; data: Record<string, unknown> } {
  if (typeof val !== "object" || val === null) return false;
  const obj = val as Record<string, unknown>;
  return (
    typeof obj.timestamp === "number" &&
    typeof obj.topic === "string" &&
    typeof obj.event === "string" &&
    typeof obj.data === "object" &&
    obj.data !== null
  );
}

/**
 * Opens a single EventSource to `/api/v1/events/stream`. Parses the unified
 * `{timestamp, topic, event, data}` envelope, filters by topic, and maintains
 * a newest-first ring buffer. Relies on native EventSource reconnection.
 */
export function useSSEv2(options: UseSSEv2Options = {}) {
  const { enabled = true, topics, bufferSize = 50, onEvent } = options;

  const [events, setEvents] = useState<SSEv2Event[]>([]);
  const [status, setStatus] = useState<"idle" | "open" | "error" | "closed">("idle");

  const esRef = useRef<EventSource | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  // Stable reference for topics to avoid unnecessary reconnections
  const topicsKey = topics ? topics.slice().sort().join(",") : "";

  const pushEvent = useCallback(
    (ev: SSEv2Event) => {
      setEvents((prev) => {
        const next = [ev, ...prev];
        return next.length > bufferSize ? next.slice(0, bufferSize) : next;
      });
    },
    [bufferSize]
  );

  useEffect(() => {
    if (!enabled) {
      setStatus("idle");
      return;
    }

    const topicSet = topicsKey ? new Set(topicsKey.split(",")) : null;

    const es = new EventSource(sseUrl("/events/stream"));
    esRef.current = es;

    es.onopen = () => {
      setStatus("open");
    };

    es.onmessage = (e: MessageEvent) => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(e.data);
      } catch {
        // Silently drop unparseable messages (forward-compatible)
        return;
      }

      if (!isValidEnvelope(parsed)) {
        // Silently drop events with unrecognized structure
        return;
      }

      // Topic filtering: if topics are specified, only pass matching events
      if (topicSet && !topicSet.has(parsed.topic)) {
        return;
      }

      const sseEvent: SSEv2Event = {
        timestamp: parsed.timestamp,
        topic: parsed.topic,
        event: parsed.event,
        data: parsed.data,
        _clientId: nextClientId(),
        _receivedAt: Date.now(),
      };

      pushEvent(sseEvent);
      onEventRef.current?.(sseEvent);
    };

    es.onerror = () => {
      // Set status to error; native EventSource will attempt reconnection
      setStatus("error");
    };

    return () => {
      es.close();
      esRef.current = null;
      setStatus("closed");
    };
  }, [enabled, topicsKey, pushEvent]);

  return { events, status };
}
