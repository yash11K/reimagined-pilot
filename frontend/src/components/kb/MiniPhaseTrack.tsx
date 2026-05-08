import { cn } from "@/lib/cn";
import {
  KB_PHASES,
  phaseIndex,
  statusToPhase,
  type DisplayStatus,
} from "@/lib/kbStatus";

export function MiniPhaseTrack({ status }: { status: DisplayStatus }) {
  const idx = phaseIndex(statusToPhase(status));
  const isFailed = status === "failed";
  const isIdle = status === "idle";

  return (
    <div className="flex items-center gap-1">
      {KB_PHASES.map((p, i) => {
        const past = i < idx;
        const current = i === idx && !isFailed && !isIdle;
        const cls = isFailed && i >= idx
          ? "bg-status-err/40"
          : past || isIdle
            ? "bg-status-ok"
            : current
              ? "bg-status-info"
              : "bg-line";
        return (
          <div
            key={p.id}
            className={cn(
              "h-1.5 w-7 rounded-full",
              cls,
              current && "ring-2 ring-status-info/30",
            )}
          />
        );
      })}
    </div>
  );
}
