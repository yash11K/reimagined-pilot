import { AlertTriangle, CheckCircle2, Clock, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { isRunning, statusLabel, type DisplayStatus } from "@/lib/kbStatus";

function LiveDot() {
  return (
    <span className="relative flex h-1.5 w-1.5">
      <span className="absolute inset-0 animate-ping rounded-full bg-status-info opacity-75" />
      <span className="relative h-1.5 w-1.5 rounded-full bg-status-info" />
    </span>
  );
}

const TONE: Record<DisplayStatus, "ok" | "warn" | "info" | "err" | "neutral"> = {
  idle: "ok",
  queued: "warn",
  discovering: "info",
  extracting: "info",
  qa: "info",
  failed: "err",
  needs_review: "warn",
};

export function SourceStatusBadge({ status }: { status: DisplayStatus }) {
  const tone = TONE[status];
  const icon =
    status === "idle" ? (
      <CheckCircle2 className="h-3 w-3" />
    ) : status === "queued" ? (
      <Clock className="h-3 w-3" />
    ) : status === "failed" ? (
      <XCircle className="h-3 w-3" />
    ) : status === "needs_review" ? (
      <AlertTriangle className="h-3 w-3" />
    ) : isRunning(status) ? (
      <LiveDot />
    ) : null;

  return (
    <Badge tone={tone}>
      {icon}
      {statusLabel(status)}
    </Badge>
  );
}
