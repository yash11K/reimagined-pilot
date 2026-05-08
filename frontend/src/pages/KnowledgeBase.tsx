import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Cpu, Database, FileText, Plus, Search } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { getStats, listSources, reingestSource } from "@/api/endpoints";
import { useBrand } from "@/contexts/BrandContext";
import { useToast } from "@/contexts/ToastContext";
import { errorWithRef } from "@/lib/errorRef";
import { fmtNum } from "@/lib/format";
import { isRunning } from "@/lib/kbStatus";
import { FilterRail, type KbFilters, type KbCounts } from "@/components/kb/FilterRail";
import { SourcesTable, type SourceRow } from "@/components/kb/SourcesTable";
import { QueueSubmitFields } from "@/components/discovery/QueueSubmitForm";

const PAGE_SIZE = 100;

export default function KnowledgeBase() {
  const { brandParam } = useBrand();
  const toast = useToast();
  const qc = useQueryClient();
  const [filters, setFilters] = useState<KbFilters>({
    status: "all",
    connector: "all",
    kbTarget: "all",
    origin: "all",
  });
  const [search, setSearch] = useState("");
  const [addOpen, setAddOpen] = useState(false);

  const stats = useQuery({ queryKey: ["stats"], queryFn: getStats });

  const reingestMut = useMutation({
    mutationFn: (id: string) => reingestSource(id),
    onSuccess: () => {
      toast.success("Re-ingest queued", "Source scheduled for ingestion");
      qc.invalidateQueries({ queryKey: ["sources"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (err: unknown) => toast.error("Re-ingest failed", errorWithRef(err)),
  });

  // Server filters: type, kb_target, origin, search. Status filtered client-side
  // until backend confirms `?status=` accepts display_status enum (today it filters
  // the raw `Source.status` column).
  const sources = useQuery({
    queryKey: [
      "sources",
      "kb",
      brandParam(),
      filters.connector,
      filters.kbTarget,
      filters.origin,
      search,
    ],
    queryFn: () =>
      listSources({
        page: 1,
        size: PAGE_SIZE,
        brand: brandParam(),
        type: filters.connector === "all" ? undefined : filters.connector,
        kb_target: filters.kbTarget === "all" ? undefined : filters.kbTarget,
        origin: filters.origin === "all" ? undefined : filters.origin,
        search: search.trim() || undefined,
        include_counts: true,
      }),
    refetchInterval: 5_000,
  });

  const rows = useMemo<SourceRow[]>(() => {
    const items = sources.data?.items ?? [];
    return items.map((s) => ({ ...s, displayStatus: s.display_status }));
  }, [sources.data]);

  const counts = useMemo<KbCounts>(() => {
    const c = sources.data?.counts;
    const total = sources.data?.total ?? 0;
    const byStatus = c?.by_status ?? {};
    const running =
      (byStatus.discovering ?? 0) + (byStatus.extracting ?? 0) + (byStatus.qa ?? 0);

    // Backend gap: by_type and by_kb_target not yet exposed. Fall back to
    // counting current page so the rail is at least populated.
    const byConnector: KbCounts["byConnector"] = {};
    const byKb: KbCounts["byKb"] = {};
    if (!c?.by_type) {
      for (const s of sources.data?.items ?? []) {
        const k = s.type as keyof KbCounts["byConnector"];
        byConnector[k] = (byConnector[k] ?? 0) + 1;
      }
    } else {
      for (const [k, v] of Object.entries(c.by_type)) {
        byConnector[k as keyof KbCounts["byConnector"]] = v;
      }
    }
    if (!c?.by_kb_target) {
      for (const s of sources.data?.items ?? []) {
        const k = s.kb_target as "public" | "internal";
        byKb[k] = (byKb[k] ?? 0) + 1;
      }
    } else {
      byKb.public = c.by_kb_target.public ?? 0;
      byKb.internal = c.by_kb_target.internal ?? 0;
    }

    return {
      all: total,
      running,
      queued: byStatus.queued ?? 0,
      idle: byStatus.idle ?? 0,
      needsReview: byStatus.needs_review ?? 0,
      failed: byStatus.failed ?? 0,
      byConnector,
      byKb,
      byOrigin: c?.by_origin ?? {},
    };
  }, [sources.data]);

  const filtered = useMemo(() => {
    return rows.filter((r) => {
      switch (filters.status) {
        case "all":
          return true;
        case "running":
          return isRunning(r.displayStatus);
        default:
          return r.displayStatus === filters.status;
      }
    });
  }, [rows, filters.status]);

  return (
    <>
      <PageHeader
        title="Knowledge Base"
        subtitle="Every URL feeding the knowledge base. Discovery surfaces new sources as siblings — there are no parent/child jobs."
        actions={
          <Button variant="primary" onClick={() => setAddOpen(true)}>
            <Plus className="h-4 w-4" /> Add sources
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi
          icon={Database}
          tone="neutral"
          label="Total sources"
          value={fmtNum(counts.all)}
          hint={`${stats.data?.sources_count ?? 0} server-wide`}
        />
        <Kpi
          icon={Cpu}
          tone="info"
          label="Currently running"
          value={fmtNum(counts.running)}
          hint={`${counts.queued} queued`}
        />
        <Kpi
          icon={FileText}
          tone="ok"
          label="Files in KB"
          value={fmtNum(stats.data?.total_files)}
          hint="from these sources"
        />
        <Kpi
          icon={AlertTriangle}
          tone="warn"
          label="Need attention"
          value={fmtNum(counts.failed + counts.needsReview)}
          hint={`${counts.failed} failed · ${counts.needsReview} review`}
        />
      </div>

      <div className="mt-6 flex gap-4">
        <FilterRail
          filters={filters}
          setFilters={setFilters}
          counts={counts}
          connectorCountsAvailable={!!sources.data?.counts?.by_type}
          kbTargetCountsAvailable={!!sources.data?.counts?.by_kb_target}
        />

        <div className="min-w-0 flex-1">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
              {fmtNum(filtered.length)} of {fmtNum(counts.all)} sources
            </div>
            <div className="ml-auto flex items-center gap-2">
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-faint" />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Filter by URL…"
                  className="h-8 w-[260px] rounded-lg border border-line bg-bg-surface pl-7 pr-3 text-xs placeholder:text-ink-faint focus:border-ink-faint focus:outline-none"
                />
              </div>
            </div>
          </div>

          {sources.isLoading ? (
            <Card className="p-8 text-center text-sm text-ink-muted">
              Loading sources…
            </Card>
          ) : (
            <SourcesTable
              sources={filtered}
              onReingest={(s) => reingestMut.mutate(s.id)}
              reingestPending={reingestMut.isPending ? reingestMut.variables ?? null : null}
            />
          )}
        </div>
      </div>

      <Modal open={addOpen} onClose={() => setAddOpen(false)} title="Add sources">
        <QueueSubmitFields onSubmitted={() => setAddOpen(false)} />
      </Modal>
    </>
  );
}

interface KpiProps {
  icon: React.ComponentType<{ className?: string }>;
  tone: "neutral" | "info" | "ok" | "warn" | "err";
  label: string;
  value: string;
  hint?: string;
}

function Kpi({ icon: Icon, tone, label, value, hint }: KpiProps) {
  const tones: Record<KpiProps["tone"], string> = {
    neutral: "text-ink-muted bg-bg-muted",
    info: "text-status-info bg-status-infoSoft",
    ok: "text-status-ok bg-status-okSoft",
    warn: "text-status-warn bg-status-warnSoft",
    err: "text-status-err bg-status-errSoft",
  };
  return (
    <Card className="flex items-center gap-3 p-4">
      <div className={`grid h-10 w-10 place-items-center rounded-lg ${tones[tone]}`}>
        <Icon className="h-5 w-5" />
      </div>
      <div className="min-w-0">
        <div className="text-[11px] font-medium uppercase tracking-wide text-ink-muted">
          {label}
        </div>
        <div className="text-xl font-semibold leading-tight tabular-nums text-ink">
          {value}
        </div>
        {hint && <div className="text-[11px] text-ink-faint">{hint}</div>}
      </div>
    </Card>
  );
}
