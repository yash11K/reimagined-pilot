import { useState, useEffect, lazy, Suspense } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Trash2,
  RefreshCw,
  Save,
  Edit3,
  CheckCircle2,
  XCircle,
  Copy,
  ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, CardBody } from "@/components/ui/Card";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Textarea, Label } from "@/components/ui/Input";
import MarkdownView from "@/components/ui/MarkdownView";
const RichTextEditor = lazy(() => import("@/components/ui/RichTextEditor"));
import {
  getFile,
  editFile,
  revalidateFile,
  deleteFile,
  approveFile,
  rejectFile,
} from "@/api/endpoints";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/contexts/ToastContext";
import { fmtDate } from "@/lib/format";

export default function FileDetail({ reviewMode = false }: { reviewMode?: boolean }) {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();

  const [editing, setEditing] = useState(false);
  const [md, setMd] = useState("");
  const [rejectNotes, setRejectNotes] = useState("");
  const [approveNotes, setApproveNotes] = useState("");

  const fileQ = useQuery({
    queryKey: ["file", id],
    queryFn: () => getFile(id!),
    enabled: !!id,
  });

  useEffect(() => {
    if (fileQ.data) setMd(fileQ.data.md_content);
  }, [fileQ.data]);

  const editMut = useMutation({
    mutationFn: () => editFile(id!, { md_content: md, reviewed_by: user.id }),
    onSuccess: () => {
      setEditing(false);
      qc.invalidateQueries({ queryKey: ["file", id] });
      toast.success("Saved", "QA re-run in background");
    },
    onError: () => toast.error("Save failed"),
  });

  const revalMut = useMutation({
    mutationFn: () => revalidateFile(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["file", id] });
      toast.success("Revalidated");
    },
    onError: () => toast.error("Revalidation failed"),
  });

  const delMut = useMutation({
    mutationFn: () => deleteFile(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["files"] });
      toast.success("File deleted", "S3 cleanup queued");
      navigate("/knowledge-library");
    },
    onError: () => toast.error("Delete failed"),
  });

  const approveMut = useMutation({
    mutationFn: () => approveFile(id!, { reviewed_by: user.id, notes: approveNotes || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["file", id] });
      qc.invalidateQueries({ queryKey: ["files"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      toast.success("Approved", "S3 upload queued");
      if (reviewMode) navigate("/review-governance");
    },
    onError: () => toast.error("Approve failed"),
  });

  const rejectMut = useMutation({
    mutationFn: () => rejectFile(id!, { reviewed_by: user.id, notes: rejectNotes }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["file", id] });
      qc.invalidateQueries({ queryKey: ["files"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      toast.warn("Rejected");
      if (reviewMode) navigate("/review-governance");
    },
    onError: () => toast.error("Reject failed"),
  });

  if (fileQ.isLoading) return <p className="text-sm text-ink-muted">Loading file…</p>;
  if (fileQ.isError || !fileQ.data)
    return <p className="text-sm text-status-err">File not found.</p>;

  const f = fileQ.data;
  const backTo = reviewMode ? "/review-governance" : "/knowledge-library";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <button
          onClick={() => navigate(backTo)}
          className="inline-flex items-center gap-1 text-xs font-medium text-ink-muted hover:text-ink"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back
        </button>
        <div className="flex items-center gap-2">
          {!reviewMode && !editing && (
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              <Edit3 className="h-3.5 w-3.5" /> Edit
            </Button>
          )}
          {!reviewMode && editing && (
            <>
              <Button variant="ghost" size="sm" onClick={() => { setEditing(false); setMd(f.md_content); }}>
                Cancel
              </Button>
              <Button variant="primary" size="sm" disabled={editMut.isPending} onClick={() => editMut.mutate()}>
                <Save className="h-3.5 w-3.5" /> Save
              </Button>
            </>
          )}
          <Button variant="outline" size="sm" disabled={revalMut.isPending} onClick={() => revalMut.mutate()}>
            <RefreshCw className={`h-3.5 w-3.5 ${revalMut.isPending ? "animate-spin" : ""}`} />
            Revalidate
          </Button>
          {!reviewMode && (
            <Button variant="danger" size="sm" disabled={delMut.isPending} onClick={() => { if (confirm("Delete this file from S3 and DB?")) delMut.mutate(); }}>
              <Trash2 className="h-3.5 w-3.5" /> Delete
            </Button>
          )}
        </div>
      </div>

      <div>
        <h1 className="text-2xl font-semibold text-ink">{f.title}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
          <Badge tone={statusTone(f.status)}>{f.status}</Badge>
          {f.kb_target && <Badge tone="info">{f.kb_target}</Badge>}
          {f.brand && <Badge tone="brand">{f.brand}</Badge>}
          {f.region && <span>· {f.region}</span>}
          {f.category && <span>· {f.category}</span>}
          <span>· updated {fmtDate(f.updated_at)}</span>
          {f.source_url && (
            <a href={f.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-ink-muted hover:text-ink">
              <ExternalLink className="h-3 w-3" /> source
            </a>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardHeader
              title="Content"
              action={
                !editing && (
                  <button
                    onClick={() => navigator.clipboard.writeText(f.md_content)}
                    className="text-ink-muted hover:text-ink"
                  >
                    <Copy className="h-3.5 w-3.5" />
                  </button>
                )
              }
            />
            <CardBody>
              {editing ? (
                <Suspense fallback={<div className="min-h-[400px] animate-pulse rounded-lg bg-bg-muted" />}>
                  <RichTextEditor
                    content={md}
                    onChange={setMd}
                    placeholder="Write your content…"
                  />
                </Suspense>
              ) : (
                <MarkdownView content={f.md_content} />
              )}
            </CardBody>
          </Card>
        </div>

        <div className="space-y-6">
          {reviewMode && (
            <Card className="border-brand/30">
              <CardHeader title="Review Decision" />
              <CardBody className="space-y-4">
                <div>
                  <Label>Approve with notes (optional)</Label>
                  <Textarea
                    value={approveNotes}
                    onChange={(e) => setApproveNotes(e.target.value)}
                    placeholder="Looks good…"
                    className="min-h-[60px] text-xs"
                  />
                  <Button
                    variant="primary"
                    className="mt-2 w-full"
                    disabled={approveMut.isPending}
                    onClick={() => approveMut.mutate()}
                  >
                    <CheckCircle2 className="h-4 w-4" /> Approve
                  </Button>
                </div>
                <div className="border-t border-line pt-4">
                  <Label>Reject reason (required)</Label>
                  <Textarea
                    value={rejectNotes}
                    onChange={(e) => setRejectNotes(e.target.value)}
                    placeholder="Content outdated…"
                    className="min-h-[60px] text-xs"
                  />
                  <Button
                    variant="danger"
                    className="mt-2 w-full"
                    disabled={rejectMut.isPending || !rejectNotes.trim()}
                    onClick={() => rejectMut.mutate()}
                  >
                    <XCircle className="h-4 w-4" /> Reject
                  </Button>
                </div>
              </CardBody>
            </Card>
          )}

          <Card>
            <CardHeader title="Sources" />
            <CardBody>
              {f.sources.length === 0 ? (
                <p className="text-xs text-ink-muted">No linked sources.</p>
              ) : (
                <div className="space-y-1.5">
                  {f.sources.map((s) => (
                    <a
                      key={s.id}
                      href={s.url}
                      target="_blank"
                      rel="noreferrer"
                      className="block truncate rounded border border-line-soft bg-bg-muted px-2 py-1.5 text-xs text-ink-soft hover:bg-bg-surface hover:text-ink"
                    >
                      {s.url}
                    </a>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>

          {f.tags?.length > 0 && (
            <Card>
              <CardHeader title="Tags" />
              <CardBody>
                <div className="flex flex-wrap gap-1.5">
                  {f.tags.map((t) => (
                    <span key={t} className="rounded bg-bg-muted px-2 py-0.5 text-xs text-ink-soft">
                      {t}
                    </span>
                  ))}
                </div>
              </CardBody>
            </Card>
          )}

          <Card>
            <CardHeader title="Quality Assessment" />
            <CardBody className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-ink-muted">Verdict:</span>
                {f.quality_verdict ? (
                  <Badge tone={statusTone(f.quality_verdict)}>{f.quality_verdict}</Badge>
                ) : (
                  <span className="text-xs text-ink-muted">—</span>
                )}
              </div>
              {f.quality_reasoning && (
                <p className="rounded-lg bg-bg-muted p-3 text-xs text-ink-soft">{f.quality_reasoning}</p>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Uniqueness" />
            <CardBody className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-ink-muted">Verdict:</span>
                {f.uniqueness_verdict ? (
                  <Badge tone={statusTone(f.uniqueness_verdict)}>{f.uniqueness_verdict}</Badge>
                ) : (
                  <span className="text-xs text-ink-muted">—</span>
                )}
              </div>
              {f.uniqueness_reasoning && (
                <p className="rounded-lg bg-bg-muted p-3 text-xs text-ink-soft">{f.uniqueness_reasoning}</p>
              )}
              {f.similar_files?.length > 0 && (
                <div>
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
                    Similar files ({f.similar_files.length})
                  </p>
                  <div className="space-y-1">
                    {f.similar_files.map((s) => (
                      <button
                        key={s.id}
                        onClick={() => navigate(`/knowledge-library/${s.id}`)}
                        className="block w-full truncate rounded border border-line-soft bg-bg-muted px-2 py-1 text-left text-xs text-ink-soft hover:bg-bg-surface hover:text-ink"
                      >
                        {s.title}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </CardBody>
          </Card>

          {f.review_notes && (
            <Card>
              <CardHeader title="Review Notes" />
              <CardBody>
                <p className="text-xs text-ink-soft">{f.review_notes}</p>
              </CardBody>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
