import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

type Tone =
  | "ok"
  | "warn"
  | "err"
  | "info"
  | "neutral"
  | "brand";

const tones: Record<Tone, string> = {
  ok: "bg-status-okSoft text-status-ok",
  warn: "bg-status-warnSoft text-status-warn",
  err: "bg-status-errSoft text-status-err",
  info: "bg-status-infoSoft text-status-info",
  neutral: "bg-status-neutralSoft text-status-neutral",
  brand: "bg-brand-soft text-brand",
};

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
        tones[tone],
        className
      )}
    >
      {children}
    </span>
  );
}

// Status helpers used by tables
export function statusTone(status: string): Tone {
  switch (status) {
    case "approved":
    case "ingested":
    case "completed":
    case "active":
    case "pass":
    case "HEALTHY":
      return "ok";
    case "pending_review":
    case "needs_confirmation":
    case "scouting":
    case "warn":
    case "processing":
      return "warn";
    case "rejected":
    case "failed":
    case "fail":
    case "CRITICAL":
    case "dismissed":
      return "err";
    default:
      return "neutral";
  }
}
