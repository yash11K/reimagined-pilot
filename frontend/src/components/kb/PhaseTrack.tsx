import { Check, Loader2, X } from "lucide-react";
import { cn } from "@/lib/cn";
import {
  KB_PHASES,
  phaseIndex,
  statusToPhase,
  type DisplayStatus,
} from "@/lib/kbStatus";

interface Props {
  status: DisplayStatus;
  progress?: number;
  hint?: string;
}

export function PhaseTrack({ status, progress = 0, hint }: Props) {
  const idx = phaseIndex(statusToPhase(status));
  const isFailed = status === "failed";
  const isIdle = status === "idle";

  return (
    <div className="rounded-xl border border-line bg-bg-surface p-5 shadow-card">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
            Pipeline
          </div>
          <div className="mt-1 text-sm text-ink-soft">
            {isFailed ? (
              <span className="text-status-err">
                Failed during {KB_PHASES[idx]?.label || "—"}
              </span>
            ) : isIdle ? (
              hint || "Up to date"
            ) : status === "queued" ? (
              "Queued — waiting for a worker"
            ) : (
              <>
                Running — <span className="font-semibold text-ink">{KB_PHASES[idx].label}</span>
              </>
            )}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[11px] uppercase tracking-wide text-ink-muted">Progress</div>
          <div className="text-2xl font-semibold tabular-nums text-ink">
            {Math.max(0, Math.min(100, progress))}%
          </div>
        </div>
      </div>

      <div className="relative">
        <div className="absolute left-0 right-0 top-5 h-0.5 bg-line" />
        <div
          className={cn(
            "absolute left-0 top-5 h-0.5 transition-all",
            isFailed ? "bg-status-err" : isIdle ? "bg-status-ok" : "bg-status-info",
          )}
          style={{ width: `${(idx / (KB_PHASES.length - 1)) * 100}%` }}
        />
        <div
          className="relative grid"
          style={{ gridTemplateColumns: `repeat(${KB_PHASES.length}, minmax(0,1fr))` }}
        >
          {KB_PHASES.map((p, i) => {
            const past = i < idx;
            const current = i === idx && !isFailed && !isIdle;
            const done = isIdle || past;
            const failed = isFailed && i === idx;

            const ring = failed
              ? "bg-status-err text-white"
              : done
                ? "bg-status-ok text-white"
                : current
                  ? "bg-status-info text-white"
                  : "bg-bg-surface text-ink-faint border-2 border-line";

            return (
              <div key={p.id} className="flex flex-col items-center gap-2">
                <div
                  className={cn(
                    "z-10 grid h-10 w-10 place-items-center rounded-full text-sm font-semibold transition-all",
                    ring,
                  )}
                >
                  {failed ? (
                    <X className="h-4 w-4" />
                  ) : done ? (
                    <Check className="h-4 w-4" />
                  ) : current ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <span>{i + 1}</span>
                  )}
                </div>
                <div className="text-center">
                  <div
                    className={cn(
                      "text-xs font-semibold",
                      failed
                        ? "text-status-err"
                        : done
                          ? "text-status-ok"
                          : current
                            ? "text-status-info"
                            : "text-ink-faint",
                    )}
                  >
                    {p.label}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
