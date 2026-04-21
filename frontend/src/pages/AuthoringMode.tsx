import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { Save, Plus, Trash2, FileText, Eye, Sparkles, PanelRightClose, PanelRightOpen } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardHeader, CardBody } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Label } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import RichTextEditor from "@/components/ui/RichTextEditor";
import { AIAssistantPanel } from "@/components/authoring/AIAssistantPanel";

interface KV {
  key: string;
  value: string;
}

interface Draft {
  id: string;
  title: string;
  body: string;
  metadata: KV[];
  updatedAt: string;
}

const STORAGE_KEY = "abg.drafts";

function loadDrafts(): Draft[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Draft[]) : [];
  } catch {
    return [];
  }
}

function saveDrafts(drafts: Draft[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(drafts));
}

function newDraft(): Draft {
  return {
    id: crypto.randomUUID(),
    title: "",
    body: "",
    metadata: [{ key: "category", value: "" }],
    updatedAt: new Date().toISOString(),
  };
}

export default function AuthoringMode() {
  const [params, setParams] = useSearchParams();
  const [drafts, setDrafts] = useState<Draft[]>(() => loadDrafts());
  const [activeId, setActiveId] = useState<string | null>(() => params.get("id"));
  const [aiOpen, setAiOpen] = useState(true);

  const active =
    drafts.find((d) => d.id === activeId) ??
    (drafts.length > 0 ? drafts[0] : null);

  useEffect(() => {
    if (active && active.id !== params.get("id")) {
      const next = new URLSearchParams(params);
      next.set("id", active.id);
      setParams(next, { replace: true });
    }
  }, [active, params, setParams]);

  const update = (patch: Partial<Draft>) => {
    if (!active) return;
    const updated: Draft = { ...active, ...patch, updatedAt: new Date().toISOString() };
    const next = drafts.map((d) => (d.id === active.id ? updated : d));
    setDrafts(next);
    saveDrafts(next);
  };

  const create = () => {
    const d = newDraft();
    const next = [d, ...drafts];
    setDrafts(next);
    saveDrafts(next);
    setActiveId(d.id);
  };

  const remove = (id: string) => {
    const next = drafts.filter((d) => d.id !== id);
    setDrafts(next);
    saveDrafts(next);
    if (id === activeId) setActiveId(next[0]?.id ?? null);
  };

  const addKv = () => update({ metadata: [...(active?.metadata ?? []), { key: "", value: "" }] });

  const setKv = (idx: number, patch: Partial<KV>) => {
    if (!active) return;
    const next = active.metadata.map((m, i) => (i === idx ? { ...m, ...patch } : m));
    update({ metadata: next });
  };

  const delKv = (idx: number) => {
    if (!active) return;
    update({ metadata: active.metadata.filter((_, i) => i !== idx) });
  };

  const handleBodyChange = useCallback(
    (md: string) => update({ body: md }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [active?.id],
  );

  const handleAIInsert = useCallback(
    (text: string) => {
      if (!active) return;
      const newBody = active.body ? active.body + "\n\n" + text : text;
      update({ body: newBody });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [active?.id, active?.body],
  );

  const words = active?.body.trim() ? active.body.trim().split(/\s+/).length : 0;
  const chars = active?.body.length ?? 0;

  return (
    <>
      <PageHeader
        title="Authoring Mode"
        subtitle="Draft articles with AI-assisted writing. Drafts are stored in your browser."
        actions={
          <>
            <Button
              variant="outline"
              onClick={() => setAiOpen(!aiOpen)}
              title={aiOpen ? "Hide AI Assistant" : "Show AI Assistant"}
            >
              {aiOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
              <Sparkles className="h-4 w-4" />
              AI Assistant
            </Button>
            <Button variant="outline" disabled={!active}>
              <Eye className="h-4 w-4" /> Preview
            </Button>
            <Button variant="primary" onClick={create}>
              <Plus className="h-4 w-4" /> New Draft
            </Button>
          </>
        }
      />

      <div className="inline-flex items-center gap-2 rounded-lg border border-status-warn/30 bg-status-warnSoft px-3 py-1.5 text-xs font-medium text-status-warn">
        <Badge tone="warn">Local only</Badge>
        Drafts never leave your browser yet. Submit path comes later.
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[220px_minmax(0,1fr)_320px]">
        {/* ── Drafts list ──────────────────────────────────────── */}
        <Card className="self-start">
          <CardHeader title="Drafts" subtitle={`${drafts.length} total`} />
          <CardBody className="space-y-1 p-2">
            {drafts.length === 0 && (
              <button
                onClick={create}
                className="flex w-full flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-line p-6 text-xs text-ink-muted hover:bg-bg-muted"
              >
                <FileText className="h-5 w-5" />
                Create first draft
              </button>
            )}
            {drafts.map((d) => (
              <div
                key={d.id}
                onClick={() => setActiveId(d.id)}
                className={`group flex cursor-pointer items-center justify-between rounded-md px-2 py-1.5 text-xs ${
                  active?.id === d.id ? "bg-bg-muted text-ink" : "text-ink-soft hover:bg-bg-muted"
                }`}
              >
                <span className="truncate">{d.title || "Untitled"}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    remove(d.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 text-ink-muted hover:text-status-err"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            ))}
          </CardBody>
        </Card>

        {/* ── Editor ──────────────────────────────────────────── */}
        <div className="space-y-4">
          {!active ? (
            <Card>
              <CardBody>
                <p className="p-12 text-center text-sm text-ink-muted">
                  No draft selected. Create one to start writing.
                </p>
              </CardBody>
            </Card>
          ) : (
            <Card>
              <CardBody className="space-y-4">
                <div>
                  <Label>Title</Label>
                  <Input
                    value={active.title}
                    onChange={(e) => update({ title: e.target.value })}
                    placeholder="Enter article title…"
                    className="text-lg font-semibold"
                  />
                </div>
                <div>
                  <Label>Content</Label>
                  <RichTextEditor
                    content={active.body}
                    onChange={handleBodyChange}
                    placeholder="Start writing your article content here…"
                    className="min-h-[420px]"
                  />
                  <p className="mt-1 text-right text-[10px] text-ink-muted">
                    {chars} characters · {words} words
                  </p>
                </div>
                <div className="flex items-center justify-between border-t border-line pt-3">
                  <span className="text-[10px] text-ink-muted">
                    Auto-saved to browser · {new Date(active.updatedAt).toLocaleTimeString()}
                  </span>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm">
                      <Save className="h-3.5 w-3.5" /> Save Draft
                    </Button>
                    <Button variant="primary" size="sm" disabled>
                      Submit for Review
                    </Button>
                  </div>
                </div>
              </CardBody>
            </Card>
          )}
        </div>

        {/* ── Right column: Metadata + AI Assistant ────────────── */}
        <div className="space-y-4">
          <Card>
            <CardHeader
              title="Article Metadata"
              subtitle="Key-value pairs. Add as many as you need."
            />
            <CardBody className="space-y-3">
              {active?.metadata.map((kv, i) => (
                <div key={i} className="flex gap-1.5">
                  <Input
                    value={kv.key}
                    onChange={(e) => setKv(i, { key: e.target.value })}
                    placeholder="key"
                    className="w-24 shrink-0 text-xs"
                  />
                  <Input
                    value={kv.value}
                    onChange={(e) => setKv(i, { value: e.target.value })}
                    placeholder="value"
                    className="flex-1 text-xs"
                  />
                  <button
                    onClick={() => delKv(i)}
                    className="grid h-9 w-9 place-items-center rounded-md text-ink-muted hover:bg-bg-muted hover:text-status-err"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
              <Button variant="outline" size="sm" className="w-full" onClick={addKv} disabled={!active}>
                <Plus className="h-3.5 w-3.5" /> Add field
              </Button>
            </CardBody>
          </Card>

          {aiOpen && active && (
            <AIAssistantPanel
              articleBody={active.body}
              onInsert={handleAIInsert}
            />
          )}
        </div>
      </div>
    </>
  );
}
