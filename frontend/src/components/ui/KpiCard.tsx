import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

interface KpiCardProps {
  label: string;
  value: string | number;
  trend?: { value: string; direction: "up" | "down" | "flat" };
  icon?: LucideIcon;
  hint?: string;
  className?: string;
  fake?: boolean;
}

export function KpiCard({
  label,
  value,
  trend,
  icon: Icon,
  hint,
  className,
  fake,
}: KpiCardProps) {
  return (
    <div
      className={cn(
        "relative rounded-xl border border-line bg-bg-surface p-5 shadow-card",
        className
      )}
    >
      {fake && (
        <span className="absolute right-3 top-3 rounded bg-status-warnSoft px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-status-warn">
          Demo
        </span>
      )}
      <div className="flex items-start justify-between">
        <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
          {label}
        </p>
        {Icon && <Icon className="h-4 w-4 text-ink-faint" />}
      </div>
      <div className="mt-2 text-3xl font-semibold tabular-nums text-ink">
        {value}
      </div>
      <div className="mt-1 flex items-center gap-2 text-xs">
        {trend && (
          <span
            className={cn(
              "font-medium",
              trend.direction === "up" && "text-status-ok",
              trend.direction === "down" && "text-status-err",
              trend.direction === "flat" && "text-ink-muted"
            )}
          >
            {trend.value}
          </span>
        )}
        {hint && <span className="text-ink-muted">{hint}</span>}
      </div>
    </div>
  );
}
