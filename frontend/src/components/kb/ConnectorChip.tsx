import { lookupConnector } from "@/lib/kbStatus";

export function ConnectorChip({ type }: { type: string }) {
  const c = lookupConnector(type);
  if (!c) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <span className="grid h-4 w-4 shrink-0 place-items-center rounded bg-ink-faint text-[9px] font-bold text-white">
          {type.slice(0, 1).toUpperCase()}
        </span>
        <span className="text-[11px] uppercase tracking-wide text-ink-muted">{type}</span>
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="grid h-4 w-4 shrink-0 place-items-center rounded text-[9px] font-bold text-white"
        style={{ background: c.color }}
      >
        {c.label.slice(0, 1)}
      </span>
      <span className="text-[11px] uppercase tracking-wide text-ink-muted">{c.label}</span>
    </span>
  );
}
