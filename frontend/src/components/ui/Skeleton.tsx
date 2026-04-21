import { cn } from "@/lib/cn";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-md bg-bg-muted",
        className
      )}
    />
  );
}

export function SkeletonRow({ cols }: { cols: number }) {
  return (
    <tr className="border-b border-line-soft">
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <Skeleton className="h-3.5 w-full" />
        </td>
      ))}
    </tr>
  );
}

export function SkeletonKpi() {
  return (
    <div className="rounded-xl border border-line bg-bg-surface p-5 shadow-card">
      <div className="flex items-start justify-between">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-4 w-4 rounded" />
      </div>
      <Skeleton className="mt-3 h-8 w-20" />
      <Skeleton className="mt-2 h-3 w-16" />
    </div>
  );
}

/** Shimmer placeholder for a progress-bar card (Test Case Performance, Search Quality) */
export function SkeletonBarChart({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-4">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i}>
          <div className="mb-1 flex items-center justify-between">
            <Skeleton className="h-3 w-32" />
            <Skeleton className="h-3 w-8" />
          </div>
          <Skeleton className="h-2 w-full rounded-full" />
        </div>
      ))}
    </div>
  );
}

/** Shimmer placeholder for activity feed items */
export function SkeletonActivity({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="flex items-start gap-3 border-b border-line-soft pb-3 last:border-0"
        >
          <Skeleton className="mt-0.5 h-4 w-4 shrink-0 rounded-full" />
          <div className="min-w-0 flex-1 space-y-1.5">
            <Skeleton className="h-3 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
          <Skeleton className="h-3 w-10 shrink-0" />
        </div>
      ))}
    </div>
  );
}

/** Shimmer for a single stat card (Source Reliability, Approved Files, etc.) */
export function SkeletonStatCard() {
  return (
    <div className="rounded-xl border border-line bg-bg-surface p-5 shadow-card">
      <Skeleton className="mb-3 h-4 w-28" />
      <div className="flex items-baseline justify-between">
        <Skeleton className="h-3 w-12" />
        <Skeleton className="h-7 w-14" />
      </div>
    </div>
  );
}
