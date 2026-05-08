import { useState, useMemo } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Rocket, X } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input, Label, Select } from "@/components/ui/Input";
import { startIngest } from "@/api/endpoints";

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

  const [region, setRegion] = useState("nam");
  const [kbTarget, setKbTarget] = useState<"public" | "internal">("public");
  const [brandOverride, setBrandOverride] = useState<string>("auto");
  const [pasteText, setPasteText] = useState("");
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const parsedPasteUrls = useMemo(() => {
    return pasteText
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter((s) => {
        try {
          return !!new URL(s).hostname;
        } catch {
          return false;
        }
      });
  }, [pasteText]);

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
      setSuccessMsg(
        `${data.jobs.length} job(s) started. Watch Discovery Tools for progress.`,
      );
      setPasteText("");
      qc.invalidateQueries({ queryKey: ["sources"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });

  const canLaunch = parsedPasteUrls.length > 0;

  return (
    <Modal open={open} onClose={onClose} title="Launch Ingestion" width="max-w-4xl">
      <div className="space-y-4">
        {/* Config row */}
        <div className="grid grid-cols-3 gap-3">
          <div>
            <Label>Region</Label>
            <Select
              value={region}
              onChange={(e) => setRegion(e.target.value)}
            >
              <option value="nam">NAM</option>
              <option value="emea">EMEA</option>
            </Select>
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
              onChange={(e) => setBrandOverride(e.target.value)}
            >
              <option value="auto">Auto-detect from URL</option>
              <option value="avis">Avis</option>
              <option value="budget">Budget</option>
              <option value="abg">ABG</option>
              <option value="none">None</option>
            </Select>
          </div>
        </div>

        <div>
          <Label>Paste AEM URLs (one per line or comma-separated)</Label>
          <textarea
            className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-xs text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
            rows={6}
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            placeholder={
              "https://www.avis.com/en/customer-service/faqs.model.json\nhttps://www.budget.com/en/help.model.json"
            }
          />
        </div>

        {parsedPasteUrls.length > 0 && (
          <div className="rounded-xl border border-line">
            <div className="flex items-center justify-between border-b border-line bg-bg-muted px-4 py-2">
              <div className="text-xs text-ink-muted">
                <span className="font-semibold text-ink">{parsedPasteUrls.length}</span>{" "}
                valid URL{parsedPasteUrls.length !== 1 && "s"} detected
              </div>
              <Button size="sm" variant="ghost" onClick={() => setPasteText("")}>
                <X className="h-3 w-3" /> Clear
              </Button>
            </div>
            <div className="max-h-48 space-y-1 overflow-y-auto scrollbar-thin p-2">
              {parsedPasteUrls.map((url, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 rounded-md bg-bg-muted px-3 py-1.5 text-xs"
                >
                  <span className="min-w-0 flex-1 truncate text-ink-soft">{url}</span>
                  <span className="shrink-0 rounded bg-brand-soft px-1.5 py-0.5 text-[9px] font-semibold text-brand">
                    {brandOverride === "auto"
                      ? (inferBrandFromUrl(url) ?? "—")
                      : brandOverride === "none"
                        ? "—"
                        : brandOverride}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {successMsg && (
          <div className="rounded-lg bg-status-okSoft p-3 text-xs text-status-ok">
            {successMsg}
          </div>
        )}
        {pasteMut.isError && (
          <div className="rounded-lg bg-status-errSoft p-3 text-xs text-status-err">
            Failed to launch ingestion.
          </div>
        )}

        <div className="flex items-center justify-between border-t border-line pt-4">
          <p className="text-[10px] text-ink-muted">
            Each pasted URL becomes a separate ingestion job.
          </p>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={!canLaunch || pasteMut.isPending}
              onClick={() => pasteMut.mutate()}
            >
              {pasteMut.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Rocket className="h-4 w-4" />
              )}
              Launch {parsedPasteUrls.length > 0 ? `(${parsedPasteUrls.length})` : ""}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
