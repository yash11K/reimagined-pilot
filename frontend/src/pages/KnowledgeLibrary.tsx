import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { FileText, CheckCircle2, FileEdit, Plus, Download } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { KpiCard } from "@/components/ui/KpiCard";
import { DataTable, Table, Thead, Th, Tbody, Tr, Td, EmptyRow } from "@/components/ui/Table";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Label, Select, Input } from "@/components/ui/Input";
import { Pagination } from "@/components/ui/Pagination";
import { SkeletonRow, SkeletonKpi } from "@/components/ui/Skeleton";
import { listFiles, listSources, getStats } from "@/api/endpoints";
import { useBrand } from "@/contexts/BrandContext";
import { fmtNum, fmtRelTime } from "@/lib/format";

export default function KnowledgeLibrary() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { brandParam } = useBrand();
  const [status, setStatus] = useState<string>("");
  const [sourceId, setSourceId] = useState<string>("");
  const [search, setSearch] = useState(params.get("search") ?? "");
  const [page, setPage] = useState(1);
  const size = 25;

  // Sync search param
  const onSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const next = new URLSearchParams(params);
    if (search) next.set("search", search);
    else next.delete("search");
    setParams(next);
  };

  const statsQ = useQuery({ queryKey: ["stats"], queryFn: getStats });

  const sourcesQ = useQuery({
    queryKey: ["sources", "picker"],
    queryFn: () => listSources({ page: 1, size: 100, parent_only: false }),
  });

  const filesQ = useQuery({
    queryKey: ["files", { brand: brandParam(), status, sourceId, search: params.get("search"), page }],
    queryFn: () =>
      listFiles({
        page,
        size,
        brand: brandParam(),
        status: status || undefined,
        source_id: sourceId || undefined,
        search: params.get("search") || undefined,
      }),
  });

  // Exclude pending_review and rejected files from default view
  // pending_review → belongs in Review & Governance
  // rejected → accessible via "Rejected" status filter
  const filteredFiles = useMemo(() => {
    if (!filesQ.data) return undefined;
    if (status) return filesQ.data; // explicit filter, show as-is
    const hidden = new Set(["pending_review", "rejected"]);
    const items = filesQ.data.items.filter((f) => !hidden.has(f.status));
    return { ...filesQ.data, items, total: items.length };
  }, [filesQ.data, status]);

  // Reset to page 1 when filters change
  const resetAnd = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setPage(1);
  };

  const drafts = useMemo(() => {
    try {
      const raw = localStorage.getItem("abg.drafts");
      return raw ? (JSON.parse(raw) as Array<{ id: string; title: string }>) : [];
    } catch {
      return [];
    }
  }, []);

  return (
    <>
      <PageHeader
        title="Knowledge Library"
        subtitle="Browse, filter, and manage all KB files."
        actions={
          <>
            <Button variant="outline">
              <Download className="h-4 w-4" /> Export
            </Button>
            <Button variant="primary" onClick={() => navigate("/authoring-mode")}>
              <Plus className="h-4 w-4" /> New Article
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {statsQ.isLoading ? (
          <>
            <SkeletonKpi />
            <SkeletonKpi />
            <SkeletonKpi />
          </>
        ) : (
          <>
            <KpiCard label="Total Articles" value={fmtNum(statsQ.data?.total_files)} icon={FileText} />
            <KpiCard label="Published" value={fmtNum(statsQ.data?.approved)} icon={CheckCircle2} />
            <KpiCard label="Drafts" value={fmtNum(drafts.length)} icon={FileEdit} hint="local drafts" />
          </>
        )}
      </div>

      <div className="mt-6">
        <DataTable>
          <div className="flex flex-wrap items-end gap-3 border-b border-line px-5 py-4">
            <form onSubmit={onSearchSubmit} className="flex-1 min-w-[200px]">
              <Label>Search</Label>
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Title or content…"
              />
            </form>
            <div className="min-w-[180px]">
              <Label>Status</Label>
              <Select value={status} onChange={(e) => resetAnd(setStatus)(e.target.value)}>
                <option value="">Active</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected / Archived</option>
                <option value="superseded">Superseded</option>
              </Select>
            </div>
            <div className="min-w-[220px]">
              <Label>Source</Label>
              <Select value={sourceId} onChange={(e) => resetAnd(setSourceId)(e.target.value)}>
                <option value="">All sources</option>
                {sourcesQ.data?.items.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.url.length > 50 ? s.url.slice(0, 50) + "…" : s.url}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          <Table>
            <Thead>
              <tr>
                <Th>Article</Th>
                <Th>Category</Th>
                <Th>Source</Th>
                <Th>Status</Th>
                <Th>Quality</Th>
                <Th>Updated</Th>
                <Th className="text-right">Actions</Th>
              </tr>
            </Thead>
            <Tbody>
              {filesQ.isLoading &&
                Array.from({ length: 6 }).map((_, i) => <SkeletonRow key={i} cols={7} />)}
              {!filesQ.isLoading && filteredFiles?.items.length === 0 && (
                <EmptyRow colSpan={7} message="No files match your filters." />
              )}
              {filteredFiles?.items.map((f) => (
                <Tr
                  key={f.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/knowledge-library/${f.id}`)}
                >
                  <Td className="max-w-sm truncate font-medium text-ink">{f.title}</Td>
                  <Td className="text-xs text-ink-muted">{f.category ?? "—"}</Td>
                  <Td className="max-w-[200px] truncate text-xs text-ink-muted">{f.source_url ?? "—"}</Td>
                  <Td>
                    <Badge tone={statusTone(f.status)}>{f.status}</Badge>
                  </Td>
                  <Td>
                    {f.quality_verdict ? (
                      <Badge tone={statusTone(f.quality_verdict)}>{f.quality_verdict}</Badge>
                    ) : (
                      <span className="text-xs text-ink-muted">—</span>
                    )}
                  </Td>
                  <Td className="text-xs text-ink-muted">{fmtRelTime(f.updated_at)}</Td>
                  <Td className="text-right">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/knowledge-library/${f.id}`);
                      }}
                    >
                      Open
                    </Button>
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>

          {filteredFiles && (
            <Pagination
              page={page}
              size={size}
              total={filteredFiles.total}
              onPage={setPage}
            />
          )}
        </DataTable>
      </div>
    </>
  );
}
