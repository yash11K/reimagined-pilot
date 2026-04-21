import { useCallback, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Radio, PauseCircle, AlertCircle } from "lucide-react";
import { Card, CardHeader, CardBody } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { useSSEv2, type SSEv2Event } from "@/hooks/useSSEv2";
import { fmtRelTime } from "@/lib/format";

/**
 * Derives a human-readable summary from a structured SSEv2 progress event.
 */
function formatLine(ev: SSEv2Event): string {
  const d = ev.data;
  switch (ev.event) {
    case "scouting_started":
      return `Scouting ${d.url ?? "unknown"}`;
    case "component_found":
      return `Found component: ${d.component ?? "unknown"}`;
    case "link_found":
      return `Found link: ${d.url ?? "unknown"}`;
    case "link_classified":
      return `Classified link: ${d.url ?? "unknown"}`;
    case "scout_complete":
      return `Scout complete for ${d.url ?? "unknown"}`;
    case "extraction_started":
      return `Extraction started for ${d.url ?? "unknown"}`;
    case "file_created":
      return `File created: ${d.filename ?? "unknown"}`;
    case "qa_complete":
      return `QA complete for ${d.url ?? "unknown"}`;
    case "job_complete":
      return `Job complete for ${d.url ?? "unknown"}`;
    case "phase_changed":
      return `Phase: ${d.phase ?? "unknown"}`;
    case "error":
      return `Error: ${d.message ?? "unknown error"}`;
    default: {
      const summary = Object.keys(d).length > 0 ? JSON.stringify(d) : "";
      return summary ? `${ev.event} · ${summary}` : ev.event;
    }
  }
}

export function LivePipelineStrip({ enabled = true }: { enabled?: boolean }) {
  const qc = useQueryClient();
  const lastInvalidate = useRef(0);

  const onEvent = useCallback(
    (_ev: SSEv2Event) => {
      // Throttle invalidations to at most once per 2s
      const now = Date.now();
      if (now - lastInvalidate.current < 2000) return;
      lastInvalidate.current = now;
      qc.invalidateQueries({ queryKey: ["sources"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
    [qc],
  );

  const { events, status } = useSSEv2({
    enabled,
    topics: ["progress"],
    bufferSize: 12,
    onEvent,
  });

  return (
    <Card>
      <CardHeader
        title="Live Pipeline"
        subtitle={
          status === "open"
            ? "Connected to backend event stream"
            : status === "error"
              ? "Connection error — retrying"
              : "Idle"
        }
        action={
          status === "open" ? (
            <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-status-ok">
              <Radio className="h-3 w-3 animate-pulse" />
              LIVE
            </span>
          ) : status === "error" ? (
            <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-status-err">
              <AlertCircle className="h-3 w-3" />
              OFFLINE
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-ink-muted">
              <PauseCircle className="h-3 w-3" />
              IDLE
            </span>
          )
        }
      />
      <CardBody className="space-y-1.5">
        {events.length === 0 && (
          <p className="text-xs text-ink-muted">
            No recent events. Launch an ingestion to see live progress.
          </p>
        )}
        {events.map((ev) => (
          <div
            key={ev._clientId}
            className={`flex items-start gap-2 border-b border-line-soft pb-1.5 text-xs last:border-0 ${
              ev.event === "error" ? "bg-status-errSoft text-status-err" : ""
            }`}
          >
            <Badge tone={ev.event === "error" ? "err" : "info"} className="mt-0.5 shrink-0">
              {ev.topic}
            </Badge>
            <span className="mt-0.5 shrink-0 rounded bg-bg-muted px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase text-ink-muted">
              {ev.event}
            </span>
            <span className="min-w-0 flex-1 truncate text-ink-soft">{formatLine(ev)}</span>
            <span className="shrink-0 text-[10px] text-ink-faint">
              {fmtRelTime(new Date(ev.timestamp).toISOString())}
            </span>
          </div>
        ))}
      </CardBody>
    </Card>
  );
}
