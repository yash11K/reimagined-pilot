import {
  CheckCircle2,
  Loader2,
  XCircle,
  AlertCircle,
  Database,
  Hash,
  Calendar,
  Clock,
} from "lucide-react";
import { Drawer } from "@/components/ui/Drawer";
import { Badge } from "@/components/ui/Badge";
import { fmtNum, fmtRelTime } from "@/lib/format";
import type { JobSummary, JobStatus } from "@/types/api";

function statusBadge(status: JobStatus) {
  switch (status) {
    case "completed":
      return (
        <Badge tone="ok">
          <CheckCircle2 className="h-3 w-3" /> Completed
        </Badge>
      );
    case "processing":
    case "scouting":
      return (
        <Badge tone="info">
          <Loader2 className="h-3 w-3 animate-spin" /> Running
        </Badge>
      );
    case "failed":
      return (
        <Badge tone="err">
          <XCircle className="h-3 w-3" /> Failed
        </Badge>
      );
    case "awaiting_confirmation":
      return (
        <Badge tone="warn">
          <AlertCircle className="h-3 w-3" /> Needs Review
        </Badge>
      );
  }
}

function Field({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 py-2">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-ink-muted" />
      <div className="min-w-0 flex-1">
        <div className="text-[11px] uppercase tracking-wide text-ink-muted">{label}</div>
        <div className="mt-0.5 break-words text-sm text-ink">{value}</div>
      </div>
    </div>
  );
}

export function JobDetailsDrawer({
  job,
  open,
  onClose,
}: {
  job: JobSummary | null;
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Drawer open={open} onClose={onClose} title={job?.source_label ?? "Job Details"}>
      {!job ? (
        <p className="text-sm text-ink-muted">No job selected.</p>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            {statusBadge(job.status)}
            <span className="text-xs text-ink-muted tabular-nums">
              {job.progress_pct}% complete
            </span>
          </div>

          <div className="h-1.5 overflow-hidden rounded-full bg-line-soft">
            <div
              className="h-full rounded-full bg-status-info transition-all"
              style={{ width: `${Math.max(0, Math.min(100, job.progress_pct))}%` }}
            />
          </div>

          <div className="divide-y divide-line">
            <Field icon={Database} label="Source" value={`${job.source_label} (${job.source_type})`} />
            <Field icon={Hash} label="Job ID" value={<code className="text-xs">{job.id}</code>} />
            <Field icon={Hash} label="Source ID" value={<code className="text-xs">{job.source_id}</code>} />
            <Field
              icon={Calendar}
              label="Started"
              value={fmtRelTime(job.started_at)}
            />
            <Field
              icon={Clock}
              label="Completed"
              value={
                job.status === "processing" || job.status === "scouting"
                  ? "In progress"
                  : fmtRelTime(job.completed_at)
              }
            />
            <Field
              icon={Hash}
              label="Discovered"
              value={fmtNum(job.discovered_count)}
            />
          </div>

          {job.error_message && (
            <div className="rounded-lg border border-status-err/30 bg-status-errSoft p-3">
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-status-err">
                Error
              </div>
              <pre className="whitespace-pre-wrap break-words text-xs text-ink">
                {job.error_message}
              </pre>
            </div>
          )}
        </div>
      )}
    </Drawer>
  );
}
