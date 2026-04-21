import { useState, useMemo, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ChevronRight,
  ChevronDown,
  Loader2,
  Rocket,
  RefreshCw,
  CheckSquare,
  Square,
  ExternalLink,
  ClipboardPaste,
  X,
} from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input, Label, Select } from "@/components/ui/Input";
import { getNavTree, startIngest } from "@/api/endpoints";
import type { NavTreeNode } from "@/types/api";
import { cn } from "@/lib/cn";

interface Selected {
  url: string; // model_json_url
  label: string;
  section: string;
  nav_label: string;
  brand: string | null;
}

/** Infer brand from a URL hostname: www.avis.* → "avis", www.budget.* → "budget", else null */
function inferBrandFromUrl(url: string): string | null {
  try {
    const host = new URL(url).hostname.toLowerCase();
    if (host.includes("avis")) return "avis";
    if (host.includes("budget")) return "budget";
  } catch {
    // invalid URL — ignore
  }
  return null;
}

export function NavTreePicker({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();

  const [mode, setMode] = useState<"tree" | "paste">("tree");

  // --- shared config ---
  const [region, setRegion] = useState("nam");
  const [kbTarget, setKbTarget] = useState<"public" | "internal">("public");
  const [brandOverride, setBrandOverride] = useState<string>("auto");
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // --- tree mode ---
  const [rootUrl, setRootUrl] = useState("");
  const [fetchUrl, setFetchUrl] = useState<string | null>(null);
  const [selected, setSelected] = useState<Record<string, Selected>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  // --- paste mode ---
  const [pasteText, setPasteText] = useState("");

  const parsedPasteUrls = useMemo(() => {
    return pasteText
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter((s) => {
        try { return !!new URL(s).hostname; } catch { return false; }
      });
  }, [pasteText]);

  const applyBrandOverride = (value: string) => {
    setBrandOverride(value);
    if (value === "auto") return; // keep per-url inferred values
    const mapped = value === "none" ? null : value;
    setSelected((prev) => {
      const next = { ...prev };
      for (const key of Object.keys(next)) {
        next[key] = { ...next[key], brand: mapped };
      }
      return next;
    });
  };

  const treeQ = useQuery({
    queryKey: ["nav-tree", fetchUrl],
    queryFn: () => getNavTree(fetchUrl!, false),
    enabled: !!fetchUrl,
    staleTime: 5 * 60 * 1000,
  });

  const ingestMut = useMutation({
    mutationFn: async () => {
      const urls = Object.values(selected).map((s) => ({
        url: s.url,
        region,
        brand: s.brand,
        nav_label: s.label,
        nav_section: s.section,
      }));
      return startIngest({
        connector_type: "aem",
        kb_target: kbTarget,
        urls,
      });
    },
    onSuccess: (data) => {
      setSuccessMsg(`${data.jobs.length} job(s) started. Watch Discovery Tools for progress.`);
      setSelected({});
      qc.invalidateQueries({ queryKey: ["sources"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });

  const pasteMut = useMutation({
    mutationFn: async () => {
      const resolveBrand = (url: string) => {
        if (brandOverride === "auto") return inferBrandFromUrl(url);
        if (brandOverride === "none") return null;
        return brandOverride;
      };
      const urls = parsedPasteUrls.map((url) => ({
        url,
        region,
        brand: resolveBrand(url),
      }));
      return startIngest({
        connector_type: "aem",
        kb_target: kbTarget,
        urls,
      });
    },
    onSuccess: (data) => {
      setSuccessMsg(`${data.jobs.length} job(s) started. Watch Discovery Tools for progress.`);
      setPasteText("");
      qc.invalidateQueries({ queryKey: ["sources"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });

  const toggleSelect = useCallback((n: NavTreeNode) => {
    if (!n.model_json_url) return;
    setSelected((prev) => {
      const next = { ...prev };
      if (next[n.model_json_url]) {
        delete next[n.model_json_url];
      } else {
        next[n.model_json_url] = {
          url: n.model_json_url,
          label: n.label,
          section: n.section,
          nav_label: n.label,
          brand: inferBrandFromUrl(n.url || n.model_json_url),
        };
      }
      return next;
    });
  }, []);

  const toggleExpand = (key: string) =>
    setExpanded((e) => ({ ...e, [key]: !e[key] }));

  const allLeaves = useMemo(() => {
    const out: NavTreeNode[] = [];
    const walk = (nodes: NavTreeNode[]) => {
      for (const n of nodes) {
        if (n.model_json_url) out.push(n);
        if (n.children?.length) walk(n.children);
      }
    };
    if (treeQ.data) walk(treeQ.data);
    return out;
  }, [treeQ.data]);

  const selectAll = () => {
    const next: Record<string, Selected> = {};
    for (const n of allLeaves) {
      next[n.model_json_url] = {
        url: n.model_json_url,
        label: n.label,
        section: n.section,
        nav_label: n.label,
        brand: inferBrandFromUrl(n.url || n.model_json_url),
      };
    }
    setSelected(next);
  };

  const clearAll = () => setSelected({});

  const onFetch = (e: React.FormEvent) => {
    e.preventDefault();
    setSuccessMsg(null);
    setSelected({});
    setFetchUrl(rootUrl.trim());
  };

  const selectedCount = Object.keys(selected).length;
  const activeMut = mode === "tree" ? ingestMut : pasteMut;
  const canLaunch =
    mode === "tree" ? selectedCount > 0 : parsedPasteUrls.length > 0;
  const launchCount =
    mode === "tree" ? selectedCount : parsedPasteUrls.length;

  return (
    <Modal open={open} onClose={onClose} title="Launch Ingestion" width="max-w-4xl">
      <div className="space-y-4">
        {/* Mode tabs */}
        <div className="flex gap-1 rounded-lg bg-bg-muted p-1">
          <button
            className={cn(
              "flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
              mode === "tree"
                ? "bg-bg text-ink shadow-sm"
                : "text-ink-muted hover:text-ink"
            )}
            onClick={() => setMode("tree")}
          >
            <RefreshCw className="mr-1.5 inline h-3 w-3" />
            Nav Tree
          </button>
          <button
            className={cn(
              "flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
              mode === "paste"
                ? "bg-bg text-ink shadow-sm"
                : "text-ink-muted hover:text-ink"
            )}
            onClick={() => setMode("paste")}
          >
            <ClipboardPaste className="mr-1.5 inline h-3 w-3" />
            Paste URLs
          </button>
        </div>

        {/* Config row (shared) */}
        <div className="grid grid-cols-3 gap-3">
          <div>
            <Label>Region</Label>
            <Input value={region} onChange={(e) => setRegion(e.target.value)} placeholder="nam" />
          </div>
          <div>
            <Label>KB Target</Label>
            <Select
              value={kbTarget}
              onChange={(e) => setKbTarget(e.target.value as "public" | "internal")}
            >
              <option value="public">Public</option>
              <option value="internal">Internal</option>
            </Select>
          </div>
          <div>
            <Label>Brand</Label>
            <Select
              value={brandOverride}
              onChange={(e) => applyBrandOverride(e.target.value)}
            >
              <option value="auto">Auto-detect from URL</option>
              <option value="avis">Avis</option>
              <option value="budget">Budget</option>
              <option value="abg">ABG</option>
              <option value="none">None</option>
            </Select>
          </div>
        </div>

        {/* ===== Tree mode ===== */}
        {mode === "tree" && (
          <>
            <form onSubmit={onFetch} className="flex items-end gap-2">
              <div className="flex-1">
                <Label>AEM Page URL</Label>
                <Input
                  value={rootUrl}
                  onChange={(e) => setRootUrl(e.target.value)}
                  placeholder="https://www.avis.com/en-us/home"
                  required
                />
              </div>
              <Button type="submit" variant="primary" disabled={treeQ.isFetching}>
                {treeQ.isFetching ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
                Fetch Tree
              </Button>
            </form>

            {treeQ.isError && (
              <div className="rounded-lg bg-status-errSoft p-3 text-xs text-status-err">
                Failed to fetch nav tree. Verify the URL points to an AEM page.
              </div>
            )}

            {treeQ.data && treeQ.data.length === 0 && (
              <div className="rounded-lg bg-bg-muted p-6 text-center text-xs text-ink-muted">
                No nav sections found on this page.
              </div>
            )}

            {treeQ.data && treeQ.data.length > 0 && (
              <div className="rounded-xl border border-line">
                <div className="flex items-center justify-between border-b border-line bg-bg-muted px-4 py-2">
                  <div className="text-xs text-ink-muted">
                    {allLeaves.length} URLs in tree · <span className="font-semibold text-ink">{selectedCount}</span> selected
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="ghost" onClick={selectAll}>
                      Select all
                    </Button>
                    <Button size="sm" variant="ghost" onClick={clearAll}>
                      Clear
                    </Button>
                  </div>
                </div>
                <div className="max-h-80 overflow-y-auto scrollbar-thin p-2">
                  {treeQ.data.map((n, i) => (
                    <TreeNode
                      key={`${n.section}-${i}`}
                      node={n}
                      depth={0}
                      keyPath={`${i}`}
                      selected={selected}
                      expanded={expanded}
                      onToggleSelect={toggleSelect}
                      onToggleExpand={toggleExpand}
                    />
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* ===== Paste mode ===== */}
        {mode === "paste" && (
          <>
            <div>
              <Label>Paste AEM URLs (one per line or comma-separated)</Label>
              <textarea
                className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-xs text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                rows={6}
                value={pasteText}
                onChange={(e) => setPasteText(e.target.value)}
                placeholder={"https://www.avis.com/en/customer-service/faqs.model.json\nhttps://www.budget.com/en/help.model.json"}
              />
            </div>

            {parsedPasteUrls.length > 0 && (
              <div className="rounded-xl border border-line">
                <div className="flex items-center justify-between border-b border-line bg-bg-muted px-4 py-2">
                  <div className="text-xs text-ink-muted">
                    <span className="font-semibold text-ink">{parsedPasteUrls.length}</span> valid URL{parsedPasteUrls.length !== 1 && "s"} detected
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => setPasteText("")}>
                    <X className="h-3 w-3" /> Clear
                  </Button>
                </div>
                <div className="max-h-48 overflow-y-auto scrollbar-thin p-2 space-y-1">
                  {parsedPasteUrls.map((url, i) => (
                    <div key={i} className="flex items-center gap-2 rounded-md bg-bg-muted px-3 py-1.5 text-xs">
                      <span className="min-w-0 flex-1 truncate text-ink-soft">{url}</span>
                      <span className="shrink-0 rounded bg-brand-soft px-1.5 py-0.5 text-[9px] font-semibold text-brand">
                        {brandOverride === "auto"
                          ? inferBrandFromUrl(url) ?? "—"
                          : brandOverride === "none"
                            ? "—"
                            : brandOverride}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {successMsg && (
          <div className="rounded-lg bg-status-okSoft p-3 text-xs text-status-ok">{successMsg}</div>
        )}
        {activeMut.isError && (
          <div className="rounded-lg bg-status-errSoft p-3 text-xs text-status-err">
            Failed to launch ingestion.
          </div>
        )}

        <div className="flex items-center justify-between border-t border-line pt-4">
          <p className="text-[10px] text-ink-muted">
            {mode === "tree"
              ? "Selected URLs are queued as separate ingestion jobs. Each goes through scout → auto-process."
              : "Each pasted URL becomes a separate ingestion job."}
          </p>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={!canLaunch || activeMut.isPending}
              onClick={() => activeMut.mutate()}
            >
              {activeMut.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Rocket className="h-4 w-4" />
              )}
              Launch {launchCount > 0 ? `(${launchCount})` : ""}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

function TreeNode({
  node,
  depth,
  keyPath,
  selected,
  expanded,
  onToggleSelect,
  onToggleExpand,
}: {
  node: NavTreeNode;
  depth: number;
  keyPath: string;
  selected: Record<string, Selected>;
  expanded: Record<string, boolean>;
  onToggleSelect: (n: NavTreeNode) => void;
  onToggleExpand: (key: string) => void;
}) {
  const hasChildren = node.children && node.children.length > 0;
  // Auto-expand top 2 levels
  const isOpen = expanded[keyPath] ?? depth < 2;
  const isSelectable = !!node.model_json_url;
  const isSelected = isSelectable && !!selected[node.model_json_url];

  return (
    <div>
      <div
        className={cn(
          "group flex items-center gap-1.5 rounded-md py-1 pr-2 text-xs",
          isSelected ? "bg-brand-soft" : "hover:bg-bg-muted"
        )}
        style={{ paddingLeft: `${depth * 16 + 4}px` }}
      >
        {hasChildren ? (
          <button
            onClick={() => onToggleExpand(keyPath)}
            className="grid h-5 w-5 place-items-center text-ink-muted hover:text-ink"
          >
            {isOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          </button>
        ) : (
          <span className="w-5" />
        )}

        {isSelectable ? (
          <button
            onClick={() => onToggleSelect(node)}
            className={cn(
              "grid h-5 w-5 place-items-center",
              isSelected ? "text-brand" : "text-ink-faint hover:text-ink"
            )}
          >
            {isSelected ? <CheckSquare className="h-3.5 w-3.5" /> : <Square className="h-3.5 w-3.5" />}
          </button>
        ) : (
          <span className="w-5" />
        )}

        <span
          className={cn(
            "min-w-0 flex-1 truncate",
            isSelected ? "font-medium text-ink" : "text-ink-soft",
            !isSelectable && "text-ink-muted"
          )}
        >
          {node.label || <em className="text-ink-faint">(unlabeled)</em>}
        </span>

        {node.section && depth === 0 && (
          <span className="shrink-0 rounded bg-bg-muted px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-ink-muted">
            {node.section}
          </span>
        )}

        {node.url && (
          <a
            href={node.url}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="shrink-0 text-ink-faint opacity-0 group-hover:opacity-100 hover:text-ink"
          >
            <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>

      {hasChildren && isOpen && (
        <div>
          {node.children.map((c, i) => (
            <TreeNode
              key={`${keyPath}-${i}`}
              node={c}
              depth={depth + 1}
              keyPath={`${keyPath}-${i}`}
              selected={selected}
              expanded={expanded}
              onToggleSelect={onToggleSelect}
              onToggleExpand={onToggleExpand}
            />
          ))}
        </div>
      )}
    </div>
  );
}
