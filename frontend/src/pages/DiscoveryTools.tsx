import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Database,
  PlayCircle,
  XCircle,
  ExternalLink,
  AlertTriangle,
  Zap,
  Compass,
  Plus,
  Settings,
  Play,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/ui/PageHeader";
import { KpiCard } from "@/components/ui/KpiCard";
import { Card, CardHeader, CardBody } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { SkeletonKpi } from "@/components/ui/Skeleton";
import { Shimmer } from "@/components/ui/Shimmer";
import { Modal } from "@/components/ui/Modal";
import {
  listSources,
  listPendingReviewSources,
  getStats,
  confirmSource,
  startIngest,
} from "@/api/endpoints";
import { useBrand } from "@/contexts/BrandContext";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/contexts/ToastContext";
import { errorWithRef } from "@/lib/errorRef";
import { fmtNum } from "@/lib/format";
import { JobsTable } from "@/components/discovery/JobsTable";
import { QueueSubmitFields } from "@/components/discovery/QueueSubmitForm";
import { RecentDiscoveries } from "@/components/discovery/RecentDiscoveries";
import { useDiscoveryLiveSync } from "@/hooks/useDiscoveryLiveSync";
import { useJobScoutStream } from "@/hooks/useJobScoutStream";
import type { KbTarget, SourceSummary } from "@/types/api";

export default function DiscoveryTools() {
  const { brandParam } = useBrand();
  const { user } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const navigate = useNavigate();

  useDiscoveryLiveSync();

  const [newJobOpen, setNewJobOpen] = useState(false);
  const scoutStream = useJobScoutStream();

  const stats = useQuery({ queryKey: ["stats"], queryFn: getStats });

  const sources = useQuery({
    queryKey: ["sources", "all", brandParam()],
    queryFn: () =>
      listSources({ page: 1, size: 25, parent_only: false, brand: brandParam() }),
  });

  const uncertain = useQuery({
    queryKey: ["sources", "pending-review"],
    queryFn: () => listPendingReviewSources(),
  });

  const confirmMut = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "process" | "discard" }) =>
      confirmSource(id, { action, reviewed_by: user.id }),
    onSuccess: (data, vars) => {
      qc.invalidateQueries({ queryKey: ["sources"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      if (vars.action === "process") {
        toast.success("Ingesting", "Source queued for processing");
        // Subscribe to per-job scout stream for real-time discovery progress
        if (data.job_id) {
          scoutStream.attach(data.job_id);
        }
      } else {
        toast.info("Discarded", "Source marked dismissed");
      }
    },
    onError: (err: unknown) => toast.error("Action failed", errorWithRef(err)),
  });

  const runAllMut = useMutation({
    mutationFn: async () => {
      const eligible = (sources.data?.items ?? []).filter(
        (s) => s.display_status === "idle" || s.display_status === "failed"
      );
      if (eligible.length === 0) return { scheduled: 0 };

      const byTarget = new Map<KbTarget, SourceSummary[]>();
      for (const s of eligible) {
        const list = byTarget.get(s.kb_target) ?? [];
        list.push(s);
        byTarget.set(s.kb_target, list);
      }

      const responses = await Promise.allSettled(
        Array.from(byTarget.entries()).map(([kb_target, group]) =>
          startIngest({
            connector_type: "aem",
            kb_target,
            urls: group.map((s) => ({
              url: s.url,
              region: s.region,
              brand: s.brand,
            })),
          })
        )
      );

      const scheduled = responses.reduce(
        (acc, r) => acc + (r.status === "fulfilled" ? r.value.jobs.length : 0),
        0
      );
      const failedGroups = responses.filter((r) => r.status === "rejected").length;
      return { scheduled, failedGroups, total: eligible.length };
    },
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      if (res.scheduled === 0) {
        toast.info("Run All Jobs", "No eligible sources to run.");
      } else {
        toast.success(
          "Run All Jobs",
          `Scheduled ${res.scheduled}/${res.total ?? res.scheduled} source(s).`
        );
      }
    },
    onError: (err: unknown) => toast.error("Run All Jobs failed", errorWithRef(err)),
  });

  const items = sources.data?.items ?? [];
  const running = items.filter(
    (s) =>
      s.display_status === "discovering" ||
      s.display_status === "extracting" ||
      s.display_status === "qa",
  ).length;

  return (
    <>
      <PageHeader
        title="Discovery Tools"
        subtitle="Automated content discovery and ingestion from connected sources across the enterprise."
        actions={
          <>
            <Button
              variant="primary"
              disabled={runAllMut.isPending || sources.isLoading}
              onClick={() => runAllMut.mutate()}
            >
              <Play className="h-4 w-4" />
              {runAllMut.isPending ? "Scheduling…" : "Run All Jobs"}
            </Button>
            <Button variant="outline" onClick={() => setNewJobOpen(true)}>
              <Compass className="h-4 w-4" /> New Discovery Job
            </Button>
            <Button variant="ghost" onClick={() => navigate("/operations")}>
              <Settings className="h-4 w-4" /> Configure Sources
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Shimmer
          loading={stats.isLoading}
          fallback={
            <>
              <SkeletonKpi />
              <SkeletonKpi />
              <SkeletonKpi />
              <SkeletonKpi />
            </>
          }
          className="contents"
        >
          <KpiCard label="Active Sources" value={fmtNum(stats.data?.sources_count)} icon={Database} />
          <KpiCard label="Running Jobs" value={fmtNum(running)} icon={PlayCircle} />
          <KpiCard
            label="Discovered Today"
            value={fmtNum(stats.data?.discovered_today)}
            icon={Plus}
            hint="rolling 24h"
          />
          <KpiCard
            label="Failed Jobs"
            value={fmtNum(stats.data?.failed_jobs_count)}
            icon={XCircle}
          />
        </Shimmer>
      </div>

      <div className="mt-6">
        <JobsTable />
      </div>

      {/* Live scout progress — appears after confirming a source */}
      {scoutStream.jobId && (
        <div className="mt-4">
          <Card>
            <CardHeader
              title="Scout Progress"
              subtitle={`Job ${scoutStream.jobId.slice(0, 8)}… — ${scoutStream.complete ? "Complete" : "Discovering…"}`}
              action={
                scoutStream.complete ? (
                  <Button size="sm" variant="ghost" onClick={() => scoutStream.detach()}>
                    Dismiss
                  </Button>
                ) : (
                  <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-status-info border-t-transparent" />
                )
              }
            />
            <CardBody>
              <div className="max-h-40 overflow-y-auto space-y-1">
                {scoutStream.scoutEvents.length === 0 && (
                  <p className="text-xs text-ink-muted">Waiting for events…</p>
                )}
                {scoutStream.scoutEvents.map((ev, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className="shrink-0 rounded bg-bg-muted px-1.5 py-0.5 font-mono text-[10px] text-ink-muted">
                      {ev.event}
                    </span>
                    <span className="truncate text-ink-soft">
                      {ev.data.url ? String(ev.data.url) : ev.data.label ? String(ev.data.label) : JSON.stringify(ev.data)}
                    </span>
                  </div>
                ))}
              </div>
            </CardBody>
          </Card>
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <RecentDiscoveries />

        <Card>
          <CardHeader
            title="Uncertain Links"
            subtitle="Confirm or discard to move forward"
            action={<AlertTriangle className="h-4 w-4 text-status-warn" />}
          />
          <CardBody>
            {uncertain.isLoading && <p className="text-xs text-ink-muted">Loading…</p>}
            {uncertain.data?.items.length === 0 && (
              <p className="text-xs text-ink-muted">All clear. No links awaiting review.</p>
            )}
            <div className="space-y-3">
              {uncertain.data?.items.map((s) => (
                <div key={s.id} className="rounded-lg border border-line-soft bg-bg-muted p-3">
                  <p className="mb-2 break-all text-xs font-medium text-ink">{s.url}</p>
                  <div className="flex items-center gap-1.5">
                    <Button
                      size="sm"
                      variant="primary"
                      disabled={confirmMut.isPending}
                      onClick={() => confirmMut.mutate({ id: s.id, action: "process" })}
                    >
                      <Zap className="h-3 w-3" /> Ingest
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={confirmMut.isPending}
                      onClick={() => confirmMut.mutate({ id: s.id, action: "discard" })}
                    >
                      Discard
                    </Button>
                    <a
                      href={s.url}
                      target="_blank"
                      rel="noreferrer"
                      className="ml-auto rounded-md p-1 text-ink-muted hover:bg-bg-surface hover:text-ink"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      </div>

      <Modal
        open={newJobOpen}
        onClose={() => setNewJobOpen(false)}
        title="New Discovery Job"
      >
        <QueueSubmitFields onSubmitted={() => setNewJobOpen(false)} />
      </Modal>
    </>
  );
}
