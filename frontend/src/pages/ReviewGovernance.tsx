import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Clock, AlertTriangle, CheckCircle2, Zap, ExternalLink } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { KpiCard } from "@/components/ui/KpiCard";
import { DataTable, Table, Thead, Th, Tbody, Tr, Td, EmptyRow } from "@/components/ui/Table";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { listFiles, listSources, confirmSource } from "@/api/endpoints";
import { useBrand } from "@/contexts/BrandContext";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/contexts/ToastContext";
import { fmtNum, fmtRelTime } from "@/lib/format";
import { cn } from "@/lib/cn";

type Tab = "files" | "sources" | "all";

export default function ReviewGovernance() {
  const navigate = useNavigate();
  const { brandParam } = useBrand();
  const { user } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("files");

  const pendingFiles = useQuery({
    queryKey: ["files", "pending", brandParam()],
    queryFn: () =>
      listFiles({
        page: 1,
        size: 50,
        status: "pending_review",
        brand: brandParam(),
      }),
  });

  const uncertainSources = useQuery({
    queryKey: ["sources", "uncertain", brandParam()],
    queryFn: () =>
      listSources({
        page: 1,
        size: 50,
        status: "needs_confirmation",
        parent_only: false,
        brand: brandParam(),
      }),
  });

  const confirmMut = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "process" | "discard" }) =>
      confirmSource(id, { action, reviewed_by: user.id }),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["sources"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      if (vars.action === "process") toast.success("Ingesting", "Source queued");
      else toast.info("Discarded");
    },
    onError: () => toast.error("Action failed"),
  });

  const filesCount = pendingFiles.data?.total ?? 0;
  const sourcesCount = uncertainSources.data?.total ?? 0;

  const tabs: { key: Tab; label: string; count: number }[] = [
    { key: "files", label: "Pending Files", count: filesCount },
    { key: "sources", label: "Uncertain Sources", count: sourcesCount },
    { key: "all", label: "All", count: filesCount + sourcesCount },
  ];

  return (
    <>
      <PageHeader
        title="Review & Governance"
        subtitle="Pending files and uncertain sources awaiting human decision."
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Pending Files" value={fmtNum(filesCount)} icon={Clock} />
        <KpiCard label="Uncertain Sources" value={fmtNum(sourcesCount)} icon={AlertTriangle} />
        <KpiCard label="Approved Today" value="—" icon={CheckCircle2} hint="coming soon" />
        <KpiCard label="Avg Review Time" value="2.3d" hint="demo" fake icon={Clock} />
      </div>

      <div className="mt-6 flex items-center gap-1 rounded-lg border border-line bg-bg-muted p-1 w-fit">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
              tab === t.key
                ? "bg-bg-surface text-ink shadow-sm"
                : "text-ink-muted hover:text-ink"
            )}
          >
            {t.label} ({t.count})
          </button>
        ))}
      </div>

      {(tab === "files" || tab === "all") && (
        <div className="mt-4">
          <DataTable>
            <div className="border-b border-line px-5 py-3 text-sm font-semibold text-ink">
              Pending Files
            </div>
            <Table>
              <Thead>
                <tr>
                  <Th>Title</Th>
                  <Th>Quality</Th>
                  <Th>Uniqueness</Th>
                  <Th>Source</Th>
                  <Th>Submitted</Th>
                  <Th className="text-right">Actions</Th>
                </tr>
              </Thead>
              <Tbody>
                {pendingFiles.data?.items.length === 0 && (
                  <EmptyRow colSpan={6} message="No files pending review." />
                )}
                {pendingFiles.data?.items.map((f) => (
                  <Tr
                    key={f.id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/review-governance/${f.id}`)}
                  >
                    <Td className="max-w-sm truncate font-medium text-ink">{f.title}</Td>
                    <Td>
                      {f.quality_verdict ? (
                        <Badge tone={statusTone(f.quality_verdict)}>{f.quality_verdict}</Badge>
                      ) : (
                        <span className="text-xs text-ink-muted">—</span>
                      )}
                    </Td>
                    <Td>
                      {f.uniqueness_verdict ? (
                        <Badge tone={statusTone(f.uniqueness_verdict)}>{f.uniqueness_verdict}</Badge>
                      ) : (
                        <span className="text-xs text-ink-muted">—</span>
                      )}
                    </Td>
                    <Td className="max-w-[200px] truncate text-xs text-ink-muted">{f.source_url ?? "—"}</Td>
                    <Td className="text-xs text-ink-muted">{fmtRelTime(f.updated_at)}</Td>
                    <Td className="text-right">
                      <Button size="sm" variant="primary" onClick={(e) => { e.stopPropagation(); navigate(`/review-governance/${f.id}`); }}>
                        Review
                      </Button>
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </DataTable>
        </div>
      )}

      {(tab === "sources" || tab === "all") && (
        <div className="mt-4">
          <DataTable>
            <div className="border-b border-line px-5 py-3 text-sm font-semibold text-ink">
              Uncertain Sources
            </div>
            <Table>
              <Thead>
                <tr>
                  <Th>URL</Th>
                  <Th>Brand</Th>
                  <Th>Region</Th>
                  <Th>Discovered</Th>
                  <Th className="text-right">Actions</Th>
                </tr>
              </Thead>
              <Tbody>
                {uncertainSources.data?.items.length === 0 && (
                  <EmptyRow colSpan={5} message="No uncertain sources." />
                )}
                {uncertainSources.data?.items.map((s) => (
                  <Tr key={s.id}>
                    <Td className="max-w-md truncate text-xs text-ink-soft">{s.url}</Td>
                    <Td className="text-xs text-ink-muted">{s.brand ?? "—"}</Td>
                    <Td className="text-xs text-ink-muted">{s.region ?? "—"}</Td>
                    <Td className="text-xs text-ink-muted">{fmtRelTime(s.created_at)}</Td>
                    <Td className="text-right">
                      <div className="inline-flex gap-1.5">
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
                          className="grid h-8 w-8 place-items-center rounded-md border border-line text-ink-muted hover:bg-bg-muted hover:text-ink"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      </div>
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </DataTable>
        </div>
      )}
    </>
  );
}
