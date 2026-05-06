// App shell — flat-source model. No tree rail; left rail is filters.

const { useState } = React;

function AppSidebar({ collapsed }) {
  const items = [
    { label: "Executive Dashboard", icon: I.Activity, key: "dash" },
    { label: "Search Operations",   icon: I.Search,   key: "search" },
    { label: "Knowledge Base",      icon: I.Database, key: "kb", active: true },
    { label: "Knowledge Library",   icon: I.FileText, key: "lib" },
    { label: "Review & Governance", icon: I.CheckCircle, key: "rev" },
    { label: "Authoring Mode",      icon: I.FileEdit, key: "auth" },
  ];
  return (
    <aside className={cn(
      "flex h-full shrink-0 flex-col border-r border-sidebar-active bg-sidebar text-sidebar-text",
      collapsed ? "w-[60px]" : "w-[220px]",
    )}>
      <div className={cn("flex items-center gap-3 px-4 py-5", collapsed && "px-3")}>
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand text-sm font-bold text-white">ABG</div>
        {!collapsed && (
          <div className="leading-tight">
            <div className="text-xs font-semibold uppercase tracking-wide text-white">Avis Budget Group</div>
            <div className="text-[11px] text-sidebar-textMuted">Knowledge System</div>
          </div>
        )}
      </div>
      <nav className="flex-1 space-y-0.5 px-2 py-2">
        {items.map(it => (
          <a key={it.key}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium",
              it.active ? "bg-sidebar-active text-white" : "text-sidebar-text hover:bg-sidebar-hover hover:text-white",
              collapsed && "justify-center px-0"
            )}
            title={collapsed ? it.label : undefined}
          >
            <it.icon className="h-4 w-4" />
            {!collapsed && <span className="truncate">{it.label}</span>}
          </a>
        ))}
      </nav>
      <div className="px-3 pb-4">
        <div className={cn("flex items-center gap-2 rounded-lg bg-sidebar-active/50 px-3 py-2", collapsed && "justify-center")}>
          <div className="grid h-7 w-7 place-items-center rounded-full bg-brand/20 text-[11px] font-semibold text-white">JM</div>
          {!collapsed && (
            <div className="min-w-0 leading-tight">
              <div className="truncate text-xs font-medium text-white">J. Morales</div>
              <div className="truncate text-[10px] text-sidebar-textMuted">KB Admin</div>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

function TopBar({ onNewIngestion, breadcrumbs }) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-bg-surface px-6">
      <div className="flex items-center gap-2 text-sm">
        {breadcrumbs.map((b, i) => (
          <React.Fragment key={i}>
            {i > 0 && <I.ChevronRight className="h-3.5 w-3.5 text-ink-faint" />}
            {b.onClick ? (
              <button onClick={b.onClick} className="text-ink-muted hover:text-ink">{b.label}</button>
            ) : (
              <span className={i === breadcrumbs.length - 1 ? "font-semibold text-ink" : "text-ink-muted"}>{b.label}</span>
            )}
          </React.Fragment>
        ))}
      </div>
      <div className="flex items-center gap-3">
        <div className="relative">
          <I.Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
          <input
            placeholder="Search sources, files…"
            className="h-9 w-[320px] rounded-lg border border-line bg-bg pl-8 pr-3 text-sm placeholder:text-ink-faint focus:border-ink-faint focus:outline-none"
          />
          <kbd className="absolute right-2 top-1/2 -translate-y-1/2 rounded border border-line bg-bg-surface px-1.5 py-0.5 text-[10px] text-ink-muted">⌘K</kbd>
        </div>
        <KbButton variant="primary" size="md" onClick={onNewIngestion}>
          <I.Plus className="h-4 w-4" />
          Add sources
        </KbButton>
      </div>
    </header>
  );
}

// Filter rail — replaces the tree
function FilterRail({ filters, setFilters, counts, density }) {
  const padY = density === "compact" ? "py-1" : "py-1.5";

  const setOne = (k, v) => setFilters(f => ({ ...f, [k]: v }));

  const RailButton = ({ active, onClick, icon: Icon, label, count, dot, disabled }) => (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "flex w-full items-center justify-between gap-2 rounded-lg px-2.5", padY,
        "text-left text-sm",
        disabled ? "text-ink-faint cursor-not-allowed" :
        active ? "bg-brand-soft font-semibold text-brand" : "text-ink-soft hover:bg-bg-muted",
      )}
    >
      <span className="flex min-w-0 items-center gap-2">
        {dot && <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", dot)} />}
        {Icon && <Icon className="h-3.5 w-3.5 shrink-0" />}
        <span className="truncate">{label}</span>
      </span>
      {count != null && (
        <span className={cn(
          "rounded-full px-1.5 py-0.5 text-[10px] tabular-nums",
          active ? "bg-brand/15 text-brand" : "bg-bg-muted text-ink-muted"
        )}>{count}</span>
      )}
    </button>
  );

  return (
    <aside className="flex h-full w-[240px] shrink-0 flex-col border-r border-line bg-bg-surface">
      <div className="px-4 pt-4 pb-2">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Filter</div>
        <div className="text-xs text-ink-faint">All sources are flat — discovery just appends siblings.</div>
      </div>

      <div className="space-y-4 overflow-y-auto px-3 pb-3 scrollbar-thin">
        <div>
          <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">Status</div>
          <div className="space-y-0.5">
            <RailButton active={filters.status === "all"}      onClick={() => setOne("status", "all")}      label="All" count={counts.all} />
            <RailButton active={filters.status === "running"}  onClick={() => setOne("status", "running")}  label="Running"      count={counts.running}  dot="bg-status-info" />
            <RailButton active={filters.status === "queued"}   onClick={() => setOne("status", "queued")}   label="Queued"       count={counts.queued}   dot="bg-status-warn" />
            <RailButton active={filters.status === "idle"}     onClick={() => setOne("status", "idle")}     label="Idle"         count={counts.idle}     dot="bg-status-ok" />
            <RailButton active={filters.status === "needs_review"} onClick={() => setOne("status", "needs_review")} label="Needs review" count={counts.needsReview} dot="bg-status-warn" />
            <RailButton active={filters.status === "failed"}   onClick={() => setOne("status", "failed")}   label="Failed"       count={counts.failed}   dot="bg-status-err" />
          </div>
        </div>

        <div>
          <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">Connector</div>
          <div className="space-y-0.5">
            <RailButton active={filters.connector === "all"} onClick={() => setOne("connector", "all")} label="All connectors" count={counts.all} />
            {window.KB_CONNECTORS.map(c => (
              <button
                key={c.id}
                disabled={!c.enabled}
                onClick={() => c.enabled && setOne("connector", c.id)}
                className={cn(
                  "flex w-full items-center justify-between gap-2 rounded-lg px-2.5", padY, "text-left text-sm",
                  !c.enabled ? "text-ink-faint cursor-not-allowed" :
                  filters.connector === c.id ? "bg-brand-soft font-semibold text-brand" : "text-ink-soft hover:bg-bg-muted",
                )}
              >
                <span className="flex min-w-0 items-center gap-2">
                  <span className="grid h-4 w-4 shrink-0 place-items-center rounded text-[9px] font-bold text-white" style={{ background: c.enabled ? c.color : "#94A3B8" }}>
                    {c.label.slice(0, 1)}
                  </span>
                  <span className="truncate">{c.label}</span>
                </span>
                {!c.enabled
                  ? <span className="rounded-full border border-line bg-bg-muted px-1.5 py-0.5 text-[9px] font-semibold uppercase text-ink-muted">Soon</span>
                  : <span className="rounded-full bg-bg-muted px-1.5 py-0.5 text-[10px] tabular-nums text-ink-muted">{counts.byConnector[c.id] || 0}</span>}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">KB target</div>
          <div className="space-y-0.5">
            <RailButton active={filters.kbTarget === "all"}      onClick={() => setOne("kbTarget", "all")}      label="Both KBs"   count={counts.all} />
            <RailButton active={filters.kbTarget === "public"}   onClick={() => setOne("kbTarget", "public")}   icon={I.Globe} label="Public"     count={counts.byKb.public || 0} />
            <RailButton active={filters.kbTarget === "internal"} onClick={() => setOne("kbTarget", "internal")} icon={I.Lock}  label="Internal"   count={counts.byKb.internal || 0} />
          </div>
        </div>

        <div>
          <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">Origin</div>
          <div className="space-y-0.5">
            <RailButton active={filters.origin === "all"}        onClick={() => setOne("origin", "all")}        label="Any"        count={counts.all} />
            <RailButton active={filters.origin === "manual"}     onClick={() => setOne("origin", "manual")}     icon={I.User}    label="Added by user" count={counts.byOrigin.manual} />
            <RailButton active={filters.origin === "discovered"} onClick={() => setOne("origin", "discovered")} icon={I.Compass} label="Discovered"    count={counts.byOrigin.discovered} />
          </div>
        </div>
      </div>
    </aside>
  );
}

Object.assign(window, { AppSidebar, TopBar, FilterRail });
