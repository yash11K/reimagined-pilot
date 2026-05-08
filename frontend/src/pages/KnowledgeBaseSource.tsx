import { useEffect, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  Compass,
  Cpu,
  ExternalLink,
  FileText,
  Globe,
  Lock,
  RefreshCw,
  Sparkles,
  XCircle,
  Zap,
} from "lucide-react";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge, statusTone } from "@/components/ui/Badge";
import { confirmSource, getSource, reingestSource } from "@/api/endpoints";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/contexts/ToastContext";
import { errorWithRef } from "@/lib/errorRef";
import { fmtRelTime } from "@/lib/format";
import { isRunning, lookupConnector, prettyUrl } from "@/lib/kbStatus";
import { ConnectorChip } from "@/components/kb/ConnectorChip";
import { PhaseTrack } from "@/components/kb/PhaseTrack";
import { SourceStatusBadge } from "@/components/kb/SourceStatusBadge";
import { useJobScoutStream } from "@/hooks/useJobScoutStream";
import type { ActiveFile, RunHistoryEntry } from "@/types/api";

export default function KnowledgeBaseSource() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { user } = useAuth();
  const toast = useToast();
  const scout = useJobScoutStream();

  const source = useQuery({
    queryKey: ["source", id],
    queryFn: () => getSource(id!),
    enabled: !!id,
    refetchInterval: 5_000,
  });

  const activeJobId = source.data?.active_job_id ?? null;
  const lastFailedRun = useMemo(
    () => source.data?.run_history.find((r) => r.status === "failed") ?? null,
    [source.data],
  );

  // Subscribe to live SSE when a job is active.
  useEffect(() => {
    if (activeJobId && scout.jobId !== activeJobId) {
      scout.attach(activeJobId);
    }
    if (!activeJobId && scout.jobId) {
      scout.detach();
    }
  }, [activeJobId, scout]);

  const confirmMut = useMutation({
    mutationFn: ({ action }: { action: "process" | "discard" }) =>
      confirmSource(id!, { action, reviewed_by: user.id }),
    onSuccess: (data, vars) => {
      qc.invalidateQueries({ queryKey: ["sources"] });
      qc.invalidateQueries({ queryKey: ["source", id] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      if (vars.action === "process") {
        toast.success("Ingesting", "Source queued for processing");
        if (data.job_id) scout.attach(data.job_id);
      } else {
        toast.info("Discarded", "Source marked dismissed");
      }
    },
    onError: (err: unknown) => toast.error("Action failed", errorWithRef(err)),
  });

  const reingestMut = useMutation({
    mutationFn: () => reingestSource(id!),
    onSuccess: (data) => {
      toast.success("Re-ingest queued", "Source scheduled for ingestion");
      qc.invalidateQueries({ queryKey: ["sources"] });
      qc.invalidateQueries({ queryKey: ["source", id] });
      if (data.job_id) scout.attach(data.job_id);
    },
    onError: (err: unknown) => toast.error("Re-ingest failed", errorWithRef(err)),
  });

  if (!id) return null;
  if (source.isLoading) {
    return (
      <Card className="p-8 text-center text-sm text-ink-muted">Loading source…</Card>
    );
  }
  if (source.isError || !source.data) {
    return (
      <Card className="p-8 text-center text-sm text-status-err">
        Source not found.
      </Card>
    );
  }

  const src = source.data;
  const display = src.display_status;
  const connector = lookupConnector(src.type);
  const progress = display === "idle" ? 100 : 0;
  const reingestBlocked = !!src.active_job_id;

  const phaseHint =
    display === "idle" && src.last_run_at
      ? `Up to date — last sync ${fmtRelTime(src.last_run_at)}`
      : undefined;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <button
            onClick={() => nav("/knowledge-base")}
            className="mb-2 inline-flex items-center gap-1 text-xs font-medium text-ink-muted hover:text-ink"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Back to sources
          </button>
          <div className="flex flex-wrap items-center gap-3">
            <SourceStatusBadge status={display} />
            <ConnectorChip type={src.type} />
            <div className="flex items-center gap-1.5 text-[11px] text-ink-muted">
              {src.kb_target === "internal" ? (
                <Lock className="h-3 w-3" />
              ) : (
                <Globe className="h-3 w-3" />
              )}
              <span className="capitalize">{src.kb_target} KB</span>
            </div>
            {connector && (
              <span className="text-[11px] text-ink-muted">{connector.fullName}</span>
            )}
            {src.runtime?.worker_id != null && (
              <div className="flex items-center gap-1.5 text-[11px] text-ink-muted">
                <Cpu className="h-3 w-3" />
                Worker #{src.runtime.worker_id}
              </div>
            )}
          </div>
          <h1 className="mt-2 break-all text-2xl font-semibold text-ink">
            {prettyUrl(src.url)}
          </h1>
          {src.parent_url && (
            <div className="mt-1.5 inline-flex items-center gap-1.5 text-xs text-ink-muted">
              <Compass className="h-3 w-3" />
              Discovered from
              <span className="font-medium text-ink-soft">
                {prettyUrl(src.parent_url)}
              </span>
            </div>
          )}
          {src.steering_prompt && (
            <div className="mt-3 inline-flex max-w-2xl items-start gap-2 rounded-lg border border-line bg-bg-muted px-3 py-2 text-xs text-ink-soft">
              <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-status-info" />
              <span>
                <span className="font-semibold">Steering: </span>
                {src.steering_prompt}
              </span>
            </div>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {display === "needs_review" && (
            <>
              <Button
                variant="primary"
                disabled={confirmMut.isPending}
                onClick={() => confirmMut.mutate({ action: "process" })}
              >
                <Zap className="h-4 w-4" /> Approve & ingest
              </Button>
              <Button
                variant="outline"
                disabled={confirmMut.isPending}
                onClick={() => confirmMut.mutate({ action: "discard" })}
              >
                <XCircle className="h-4 w-4" /> Discard
              </Button>
            </>
          )}
          {(display === "idle" || display === "failed") && (
            <Button
              variant="primary"
              disabled={reingestMut.isPending || reingestBlocked}
              title={reingestBlocked ? "An ingestion is already running" : undefined}
              onClick={() => reingestMut.mutate()}
            >
              <RefreshCw className="h-4 w-4" />
              {reingestMut.isPending
                ? "Scheduling…"
                : display === "failed"
                  ? "Retry"
                  : "Re-ingest"}
            </Button>
          )}
          <a
            href={src.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-line bg-bg-surface px-4 text-sm font-medium text-ink hover:bg-bg-muted"
          >
            <ExternalLink className="h-4 w-4" /> Open URL
          </a>
        </div>
      </div>

      {/* Phase track — hide for needs_review */}
      {display !== "needs_review" && (
        <PhaseTrack status={display} progress={progress} hint={phaseHint} />
      )}

      {/* Body — variant by status */}
      {display === "queued" && <QueuedView position={src.runtime?.queue_position} />}

      {display === "needs_review" && <NeedsReviewBanner />}

      {isRunning(display) && <LiveStreamCard scoutEvents={scout.scoutEvents} />}

      {display === "failed" && (
        <FailedView
          error={
            lastFailedRun
              ? `Last run failed ${fmtRelTime(lastFailedRun.completed_at ?? lastFailedRun.started_at)}.`
              : "Unknown error during ingestion."
          }
        />
      )}

      {display === "idle" && (
        <>
          <Card>
            <CardHeader title="Last sync" subtitle={fmtRelTime(src.last_run_at)} />
            <CardBody>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <Stat label="Files total" value={src.file_stats.total} tone="neutral" />
                <Stat label="Approved" value={src.file_stats.approved} tone="ok" />
                <Stat label="Pending" value={src.file_stats.pending} tone="warn" />
                <Stat label="Rejected" value={src.file_stats.rejected} tone="err" />
              </div>
            </CardBody>
          </Card>

          <ActiveFilesCard files={src.active_files} />
        </>
      )}

      <RunHistoryCard runs={src.run_history} runCount={src.run_count} />
    </div>
  );
}

function QueuedView({ position }: { position: number | null | undefined }) {
  return (
    <Card>
      <CardBody className="flex items-center justify-center py-10">
        <div className="text-center">
          <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-status-warnSoft text-status-warn">
            <Clock className="h-8 w-8" />
          </div>
          <div className="mt-4 text-lg font-semibold text-ink">Waiting for a worker</div>
          <div className="mt-1 text-sm text-ink-muted">
            {position != null ? (
              <>
                Position <span className="font-semibold text-ink">#{position}</span> in the queue.
              </>
            ) : (
              "Queued. Will start as soon as a worker is free."
            )}
          </div>
        </div>
      </CardBody>
    </Card>
  );
}

function NeedsReviewBanner() {
  return (
    <Card className="border-status-warn/30 bg-status-warnSoft/30">
      <CardBody>
        <div className="flex items-start gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-status-warn text-white">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div className="flex-1">
            <div className="text-sm font-semibold text-status-warn">
              This source was flagged uncertain during discovery
            </div>
            <div className="mt-1 text-sm text-ink">
              Approve to ingest it, or discard if it shouldn't be in the knowledge base.
            </div>
          </div>
        </div>
      </CardBody>
    </Card>
  );
}

interface ScoutEvent {
  event: string;
  data: Record<string, unknown>;
  at: number;
}

function LiveStreamCard({ scoutEvents }: { scoutEvents: ScoutEvent[] }) {
  return (
    <Card>
      <CardHeader
        title="Activity"
        subtitle={`${scoutEvents.length} update${scoutEvents.length === 1 ? "" : "s"} · live stream from the ingestion worker`}
        action={
          <span className="inline-flex items-center gap-1 rounded-full bg-status-infoSoft px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-status-info">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inset-0 animate-ping rounded-full bg-status-info opacity-75" />
              <span className="relative h-1.5 w-1.5 rounded-full bg-status-info" />
            </span>
            Live
          </span>
        }
      />
      <CardBody className="max-h-[420px] overflow-y-auto">
        {scoutEvents.length === 0 ? (
          <div className="py-6 text-xs text-ink-muted">Waiting for events…</div>
        ) : (
          <div className="space-y-1">
            {scoutEvents.map((ev, i) => {
              const url = (ev.data.url as string | undefined) ?? null;
              const label =
                (ev.data.label as string | undefined) ??
                (ev.data.title as string | undefined) ??
                null;
              return (
                <div key={i} className="flex items-start gap-2 text-xs">
                  <span className="shrink-0 rounded bg-bg-muted px-1.5 py-0.5 font-mono text-[10px] text-ink-muted">
                    {ev.event}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-ink-soft">
                    {label || url || JSON.stringify(ev.data)}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function FailedView({ error }: { error: string }) {
  return (
    <Card className="border-status-err/30 bg-status-errSoft/40">
      <CardBody>
        <div className="flex items-start gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-status-err text-white">
            <XCircle className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-status-err">
              Last ingestion failed
            </div>
            <div className="mt-1 text-sm text-ink">{error}</div>
          </div>
        </div>
      </CardBody>
    </Card>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "ok" | "warn" | "err" | "info" | "neutral";
}) {
  const tones: Record<typeof tone, string> = {
    neutral: "text-ink",
    ok: "text-status-ok",
    warn: "text-status-warn",
    err: "text-status-err",
    info: "text-status-info",
  };
  return (
    <div className="rounded-lg bg-bg-muted px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-ink-muted">{label}</div>
      <div className={`mt-0.5 text-xl font-semibold tabular-nums ${tones[tone]}`}>
        {value}
      </div>
    </div>
  );
}

function ActiveFilesCard({ files }: { files: ActiveFile[] }) {
  return (
    <Card>
      <CardHeader
        title="Active files"
        subtitle={`${files.length} file${files.length === 1 ? "" : "s"} currently in KB`}
      />
      <CardBody className="px-0 pb-0">
        {files.length === 0 ? (
          <div className="px-4 py-8 text-center text-xs text-ink-muted">
            No active files for this source yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg-muted text-left text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
                <tr>
                  <th className="px-4 py-2.5">Title</th>
                  <th className="px-4 py-2.5">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {files.map((f) => (
                  <tr key={f.id} className="hover:bg-bg-muted/60">
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2 text-ink">
                        <FileText className="h-3.5 w-3.5 shrink-0 text-ink-faint" />
                        <span className="truncate">{f.title}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge tone={statusTone(f.status)}>{f.status}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function RunHistoryCard({
  runs,
  runCount,
}: {
  runs: RunHistoryEntry[];
  runCount: number;
}) {
  return (
    <Card>
      <CardHeader
        title="Run history"
        subtitle={`${runCount} run${runCount === 1 ? "" : "s"} total`}
      />
      <CardBody>
        {runs.length === 0 ? (
          <div className="text-xs text-ink-muted">No prior runs yet.</div>
        ) : (
          <ol className="space-y-2">
            {runs.map((r) => (
              <li
                key={r.id}
                className="flex items-center gap-3 rounded-lg border border-line-soft bg-bg-muted/40 px-3 py-2"
              >
                <span
                  className={`h-2 w-2 shrink-0 rounded-full ${
                    r.status === "failed"
                      ? "bg-status-err"
                      : r.status === "completed"
                        ? "bg-status-ok"
                        : "bg-status-info"
                  }`}
                />
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium text-ink">
                    {fmtRelTime(r.completed_at ?? r.started_at)}
                  </div>
                  <div className="text-[10.5px] text-ink-muted capitalize">{r.status}</div>
                </div>
                {r.status === "completed" && (
                  <CheckCircle2 className="h-3.5 w-3.5 text-status-ok" />
                )}
                {r.status === "failed" && (
                  <XCircle className="h-3.5 w-3.5 text-status-err" />
                )}
              </li>
            ))}
          </ol>
        )}
      </CardBody>
    </Card>
  );
}
