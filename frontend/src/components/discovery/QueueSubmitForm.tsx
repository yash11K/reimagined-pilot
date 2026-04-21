import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, HelpCircle } from "lucide-react";
import { submitToQueue } from "@/api/endpoints";
import { useToast } from "@/contexts/ToastContext";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Input";
import { Input, Label } from "@/components/ui/Input";

export function QueueSubmitFields({ onSubmitted }: { onSubmitted?: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();

  const [urls, setUrls] = useState("");
  const [priority, setPriority] = useState(0);

  const mutation = useMutation({
    mutationFn: submitToQueue,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["queue"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      const msg = `Queued: ${data.queued}, Skipped: ${data.skipped}`;
      if (data.skipped > 0) {
        toast.warn("Queue Submission", msg);
      } else {
        toast.success("Queue Submission", msg);
      }
      setUrls("");
      setPriority(0);
      onSubmitted?.();
    },
    onError: (err: Error) => {
      toast.error("Queue Submission Failed", err.message);
    },
  });

  const handleSubmit = () => {
    const parsed = urls
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    if (parsed.length === 0) return;
    mutation.mutate({ urls: parsed, priority });
  };

  return (
    <div className="space-y-4">
      <div>
        <Label htmlFor="queue-urls">URLs (one per line)</Label>
        <Textarea
          id="queue-urls"
          placeholder={"https://example.com/page-1\nhttps://example.com/page-2"}
          value={urls}
          onChange={(e) => setUrls(e.target.value)}
          rows={4}
        />
      </div>

      <div className="flex items-end gap-3">
        <div className="w-32">
          <Label htmlFor="queue-priority">Priority</Label>
          <div className="relative">
            <Input
              id="queue-priority"
              type="number"
              min={0}
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value))}
            />
            <div className="group absolute right-2 top-1/2 -translate-y-1/2">
              <HelpCircle className="h-3.5 w-3.5 text-ink-muted cursor-help" />
              <div className="pointer-events-none absolute bottom-full right-0 mb-2 hidden w-48 rounded-lg border border-line bg-bg-surface p-2 text-xs text-ink-muted shadow-card group-hover:block">
                Higher values are processed first. Default is 0.
              </div>
            </div>
          </div>
        </div>

        <Button
          variant="primary"
          size="md"
          disabled={mutation.isPending || urls.trim().length === 0}
          onClick={handleSubmit}
        >
          {mutation.isPending ? "Submitting…" : "Add to Queue"}
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
        Add URLs to Queue
      </button>

      {open && (
        <div className="px-4 pb-4">
          <QueueSubmitFields />
        </div>
      )}
    </div>
  );
}
