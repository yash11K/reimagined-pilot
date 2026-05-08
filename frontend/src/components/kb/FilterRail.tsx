import { Compass, Globe, Lock, User, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";
import { KB_CONNECTORS, type KbConnectorId } from "@/lib/kbStatus";

export type StatusFilter = "all" | "running" | "queued" | "idle" | "needs_review" | "failed";
export type ConnectorFilter = "all" | KbConnectorId;
export type KbTargetFilter = "all" | "public" | "internal";
export type OriginFilter = "all" | "manual" | "discovered";

export interface KbFilters {
  status: StatusFilter;
  connector: ConnectorFilter;
  kbTarget: KbTargetFilter;
  origin: OriginFilter;
}

export interface KbCounts {
  all: number;
  running: number;
  queued: number;
  idle: number;
  needsReview: number;
  failed: number;
  byConnector: Partial<Record<KbConnectorId, number>>;
  byKb: Partial<Record<"public" | "internal", number>>;
  byOrigin: Partial<Record<"manual" | "discovered", number>>;
}

interface Props {
  filters: KbFilters;
  setFilters: (f: KbFilters) => void;
  counts: KbCounts;
  /** When true, badges next to Connector / KB target hide because backend
   * does not yet return `by_type` / `by_kb_target`. Phase 3 unblocks. */
  connectorCountsAvailable?: boolean;
  kbTargetCountsAvailable?: boolean;
}

export function FilterRail({
  filters,
  setFilters,
  counts,
  connectorCountsAvailable,
  kbTargetCountsAvailable,
}: Props) {
  const setOne = <K extends keyof KbFilters>(k: K, v: KbFilters[K]) =>
    setFilters({ ...filters, [k]: v });

  return (
    <aside className="flex w-[240px] shrink-0 flex-col self-start rounded-xl border border-line bg-bg-surface shadow-card">
      <div className="px-4 pt-4 pb-2">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
          Filter
        </div>
        <div className="text-xs text-ink-faint">
          All sources are flat — discovery appends siblings.
        </div>
      </div>

      <div className="space-y-4 overflow-y-auto px-3 pb-3">
        <Section title="Status">
          <RailButton
            active={filters.status === "all"}
            onClick={() => setOne("status", "all")}
            label="All"
            count={counts.all}
          />
          <RailButton
            active={filters.status === "running"}
            onClick={() => setOne("status", "running")}
            label="Running"
            count={counts.running}
            dot="bg-status-info"
          />
          <RailButton
            active={filters.status === "queued"}
            onClick={() => setOne("status", "queued")}
            label="Queued"
            count={counts.queued}
            dot="bg-status-warn"
          />
          <RailButton
            active={filters.status === "idle"}
            onClick={() => setOne("status", "idle")}
            label="Idle"
            count={counts.idle}
            dot="bg-status-ok"
          />
          <RailButton
            active={filters.status === "needs_review"}
            onClick={() => setOne("status", "needs_review")}
            label="Needs review"
            count={counts.needsReview}
            dot="bg-status-warn"
          />
          <RailButton
            active={filters.status === "failed"}
            onClick={() => setOne("status", "failed")}
            label="Failed"
            count={counts.failed}
            dot="bg-status-err"
          />
        </Section>

        <Section title="Connector">
          <RailButton
            active={filters.connector === "all"}
            onClick={() => setOne("connector", "all")}
            label="All connectors"
            count={connectorCountsAvailable ? counts.all : undefined}
          />
          {KB_CONNECTORS.map((c) => (
            <button
              key={c.id}
              disabled={!c.enabled}
              onClick={() => c.enabled && setOne("connector", c.id)}
              className={cn(
                "flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm",
                !c.enabled
                  ? "cursor-not-allowed text-ink-faint"
                  : filters.connector === c.id
                    ? "bg-brand-soft font-semibold text-brand"
                    : "text-ink-soft hover:bg-bg-muted",
              )}
            >
              <span className="flex min-w-0 items-center gap-2">
                <span
                  className="grid h-4 w-4 shrink-0 place-items-center rounded text-[9px] font-bold text-white"
                  style={{ background: c.enabled ? c.color : "#94A3B8" }}
                >
                  {c.label.slice(0, 1)}
                </span>
                <span className="truncate">{c.label}</span>
              </span>
              {!c.enabled ? (
                <span className="rounded-full border border-line bg-bg-muted px-1.5 py-0.5 text-[9px] font-semibold uppercase text-ink-muted">
                  Soon
                </span>
              ) : connectorCountsAvailable ? (
                <span
                  className={cn(
                    "rounded-full px-1.5 py-0.5 text-[10px] tabular-nums",
                    filters.connector === c.id
                      ? "bg-brand/15 text-brand"
                      : "bg-bg-muted text-ink-muted",
                  )}
                >
                  {counts.byConnector[c.id] || 0}
                </span>
              ) : null}
            </button>
          ))}
        </Section>

        <Section title="KB target">
          <RailButton
            active={filters.kbTarget === "all"}
            onClick={() => setOne("kbTarget", "all")}
            label="Both KBs"
            count={kbTargetCountsAvailable ? counts.all : undefined}
          />
          <RailButton
            active={filters.kbTarget === "public"}
            onClick={() => setOne("kbTarget", "public")}
            icon={Globe}
            label="Public"
            count={kbTargetCountsAvailable ? counts.byKb.public || 0 : undefined}
          />
          <RailButton
            active={filters.kbTarget === "internal"}
            onClick={() => setOne("kbTarget", "internal")}
            icon={Lock}
            label="Internal"
            count={kbTargetCountsAvailable ? counts.byKb.internal || 0 : undefined}
          />
        </Section>

        <Section title="Origin">
          <RailButton
            active={filters.origin === "all"}
            onClick={() => setOne("origin", "all")}
            label="Any"
            count={counts.all}
          />
          <RailButton
            active={filters.origin === "manual"}
            onClick={() => setOne("origin", "manual")}
            icon={User}
            label="Added by user"
            count={counts.byOrigin.manual || 0}
          />
          <RailButton
            active={filters.origin === "discovered"}
            onClick={() => setOne("origin", "discovered")}
            icon={Compass}
            label="Discovered"
            count={counts.byOrigin.discovered || 0}
          />
        </Section>
      </div>
    </aside>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
        {title}
      </div>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

interface RailButtonProps {
  active: boolean;
  onClick: () => void;
  label: string;
  count?: number;
  dot?: string;
  icon?: LucideIcon;
}

function RailButton({ active, onClick, label, count, dot, icon: Icon }: RailButtonProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm",
        active
          ? "bg-brand-soft font-semibold text-brand"
          : "text-ink-soft hover:bg-bg-muted",
      )}
    >
      <span className="flex min-w-0 items-center gap-2">
        {dot && <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", dot)} />}
        {Icon && <Icon className="h-3.5 w-3.5 shrink-0" />}
        <span className="truncate">{label}</span>
      </span>
      {count != null && (
        <span
          className={cn(
            "rounded-full px-1.5 py-0.5 text-[10px] tabular-nums",
            active ? "bg-brand/15 text-brand" : "bg-bg-muted text-ink-muted",
          )}
        >
          {count}
        </span>
      )}
    </button>
  );
}
