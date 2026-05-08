import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";
import { startIngest } from "@/api/endpoints";
import { useToast } from "@/contexts/ToastContext";
import { Button } from "@/components/ui/Button";
import { Textarea, Label, Select } from "@/components/ui/Input";
import { errorWithRef } from "@/lib/errorRef";
import type { KbTarget } from "@/types/api";

export function QueueSubmitFields({ onSubmitted }: { onSubmitted?: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();

  const [urls, setUrls] = useState("");
  const [kbTarget, setKbTarget] = useState<KbTarget>("public");

  const mutation = useMutation({
    mutationFn: startIngest,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["sources"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      toast.success("Ingest scheduled", `${data.jobs.length} job(s) queued`);
      setUrls("");
      onSubmitted?.();
    },
    onError: (err: unknown) => {
      toast.error("Ingest failed", errorWithRef(err));
    },
  });

  const handleSubmit = () => {
    const parsed = urls
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    if (parsed.length === 0) return;
    mutation.mutate({
      connector_type: "aem",
      kb_target: kbTarget,
      urls: parsed.map((url) => ({ url })),
    });
  };

  return (
    <div className="space-y-4">
      <div>
        <Label htmlFor="ingest-urls">URLs (one per line)</Label>
        <Textarea
          id="ingest-urls"
          placeholder={"https://example.com/page-1\nhttps://example.com/page-2"}
          value={urls}
          onChange={(e) => setUrls(e.target.value)}
          rows={4}
        />
      </div>

      <div className="flex items-end gap-3">
        <div className="w-40">
          <Label htmlFor="ingest-kb-target">KB target</Label>
          <Select
            id="ingest-kb-target"
            value={kbTarget}
            onChange={(e) => setKbTarget(e.target.value as KbTarget)}
          >
            <option value="public">Public</option>
            <option value="internal">Internal</option>
          </Select>
        </div>

        <Button
          variant="primary"
          size="md"
          disabled={mutation.isPending || urls.trim().length === 0}
          onClick={handleSubmit}
        >
          {mutation.isPending ? "Submitting…" : "Start ingest"}
        </Button>
      </div>
    </div>
  );
}

export function QueueSubmitForm() {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-xl border border-line bg-bg-surface">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 p-4 text-left text-sm font-semibold text-ink hover:bg-bg-muted/50 transition-colors rounded-xl"
      >
        {open ? (
          <ChevronDown className="h-4 w-4 text-ink-muted" />
        ) : (
          <ChevronRight className="h-4 w-4 text-ink-muted" />
        )}
        Add URLs
      </button>

      {open && (
        <div className="px-4 pb-4">
          <QueueSubmitFields />
        </div>
      )}
    </div>
  );
}
