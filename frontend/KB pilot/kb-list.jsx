// Sources list page — every row is a source. No jobs.

const { useState: useState_L, useMemo: useMemo_L } = React;

function ListKpi({ icon: Icon, label, value, hint, tone = "neutral" }) {
  const tones = {
    neutral: "text-ink-muted bg-bg-muted",
    info: "text-status-info bg-status-infoSoft",
    ok: "text-status-ok bg-status-okSoft",
    warn: "text-status-warn bg-status-warnSoft",
    err: "text-status-err bg-status-errSoft",
  };
  return (
    <div className="flex items-center gap-3 rounded-xl border border-line bg-bg-surface p-4 shadow-card">
      <div className={cn("grid h-10 w-10 place-items-center rounded-lg", tones[tone])}>
        <Icon className="h-5 w-5" />
      </div>
      <div className="min-w-0">
        <div className="text-[11px] font-medium uppercase tracking-wide text-ink-muted">{label}</div>
        <div className="font-semibold text-ink text-xl tabular-nums leading-tight">{value}</div>
        {hint && <div className="text-[11px] text-ink-faint">{hint}</div>}
      </div>
    </div>
  );
}

// Source-status badge — tones differ from old job badge
function SourceStatusBadge({ status }) {
  const map = {
    idle:         { tone: "ok",      label: "Idle",         icon: <I.CheckCircle className="h-3 w-3" /> },
    queued:       { tone: "warn",    label: "Queued",       icon: <I.Clock className="h-3 w-3" /> },
    discovering:  { tone: "info",    label: "Discovering",  icon: <LiveDot /> },
    extracting:   { tone: "info",    label: "Extracting",   icon: <LiveDot /> },
    qa:           { tone: "info",    label: "QA",           icon: <LiveDot /> },
    failed:       { tone: "err",     label: "Failed",       icon: <I.XCircle className="h-3 w-3" /> },
    needs_review: { tone: "warn",    label: "Needs review", icon: <I.AlertTriangle className="h-3 w-3" /> },
  };
  const m = map[status] || { tone: "neutral", label: status };
  return <KbBadge tone={m.tone}>{m.icon}{m.label}</KbBadge>;
}
function LiveDot() {
  return (
    <span className="relative flex h-1.5 w-1.5">
      <span className="absolute inset-0 animate-ping rounded-full bg-status-info opacity-75" />
      <span className="relative h-1.5 w-1.5 rounded-full bg-status-info" />
    </span>
  );
}

function MiniPhaseTrack({ source }) {
  const phase = window.kbStatusToPhase(source.status);
  const idx = window.kbPhaseIndex(phase);
  const isFailed = source.status === "failed";
  const isIdle = source.status === "idle";
  return (
    <div className="flex items-center gap-1">
      {window.KB_PHASES.map((p, i) => {
        const past = i < idx;
        const current = i === idx && !isFailed && !isIdle;
        const cls = isFailed && i >= idx
          ? "bg-status-err/40"
          : (past || isIdle)
            ? "bg-status-ok"
            : current
              ? "bg-status-info"
              : "bg-line";
        return <div key={p.id} className={cn("h-1.5 w-7 rounded-full", cls, current && "ring-2 ring-status-info/30")} />;
      })}
    </div>
  );
}

function prettyUrl(url) {
  try {
    const u = new URL(url);
    return (u.hostname.replace(/^www\./, "") + u.pathname).replace(/\/$/, "") || u.hostname;
  } catch { return url; }
}

function ConnectorChip({ connectorId }) {
  const c = window.KB_CONNECTORS.find(x => x.id === connectorId);
  if (!c) return null;
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="grid h-4 w-4 shrink-0 place-items-center rounded text-[9px] font-bold text-white" style={{ background: c.color }}>{c.label.slice(0, 1)}</span>
      <span className="text-[11px] uppercase tracking-wide text-ink-muted">{c.label}</span>
    </span>
  );
}

// ---- Sources table ---------------------------------------------------------
function SourcesTable({ sources, onOpen, onReingest, density }) {
  const cellPad = density === "compact" ? "px-3 py-2" : "px-4 py-3";
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-bg-surface shadow-card">
      <div className="overflow-x-auto scrollbar-thin">
        <table className="w-full text-sm">
          <thead className="bg-sidebar text-left text-[11px] font-semibold uppercase tracking-wider text-sidebar-text">
            <tr>
              <th className={cn("font-semibold", cellPad)}>Source</th>
              <th className={cn("font-semibold", cellPad)}>Status</th>
              <th className={cn("font-semibold", cellPad)}>Pipeline</th>
              <th className={cn("font-semibold text-right", cellPad)}>Files</th>
              <th className={cn("font-semibold", cellPad)}>Last sync</th>
              <th className={cn("font-semibold", cellPad)}>Added</th>
              <th className={cn("font-semibold text-right", cellPad)}>Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {sources.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-12 text-center text-sm text-ink-muted">
                No sources match your filters.
              </td></tr>
            )}
            {sources.map(src => {
              const discoveredFromSrc = src.discoveredFrom ? window.KB_SOURCES.find(s => s.id === src.discoveredFrom) : null;
              return (
                <tr key={src.id} className="cursor-pointer transition-colors hover:bg-bg-muted/60" onClick={() => onOpen(src)}>
                  <td className={cellPad}>
                    <div className="flex items-center gap-2.5">
                      <ConnectorChip connectorId={src.connector} />
                      {src.kbTarget === "internal"
                        ? <I.Lock className="h-3 w-3 text-ink-faint" />
                        : <I.Globe className="h-3 w-3 text-ink-faint" />}
                    </div>
                    <div className="mt-1 max-w-[360px] truncate text-sm font-medium text-ink">{prettyUrl(src.url)}</div>
                    {discoveredFromSrc && (
                      <div className="mt-0.5 inline-flex items-center gap-1 text-[10.5px] text-ink-muted">
                        <I.Compass className="h-2.5 w-2.5" />
                        Discovered from {prettyUrl(discoveredFromSrc.url)}
                      </div>
                    )}
                  </td>
                  <td className={cellPad}><SourceStatusBadge status={src.status} /></td>
                  <td className={cellPad}><MiniPhaseTrack source={src} /></td>
                  <td className={cn("text-right tabular-nums text-ink-soft", cellPad)}>
                    {src.files > 0 ? <span className="font-semibold text-ink">{window.kbFmtNum(src.files)}</span> : <span className="text-ink-faint">—</span>}
                  </td>
                  <td className={cn("text-xs text-ink-muted", cellPad)}>
                    {src.lastRun
                      ? <>
                          <div className="text-ink-soft">{window.kbFmtRel(src.lastRun.at)}</div>
                          <div className="text-[10px] text-ink-faint">
                            {src.lastRun.status === "failed"
                              ? <span className="text-status-err">failed</span>
                              : <>+{src.lastRun.created} · ~{src.lastRun.replaced || 0}</>}
                          </div>
                        </>
                      : <span className="text-ink-faint">never</span>}
                  </td>
                  <td className={cn("text-xs text-ink-muted", cellPad)}>
                    <div>{window.kbFmtRel(src.addedAt)}</div>
                    <div className="text-[10px] text-ink-faint">by {(src.addedBy || "").split("@")[0]}</div>
                  </td>
                  <td className={cn("text-right", cellPad)} onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center justify-end gap-1">
                      {src.status === "idle" || src.status === "failed" || src.status === "needs_review" ? (
                        <KbButton size="sm" variant="outline" onClick={() => onReingest(src)}>
                          <I.RefreshCw className="h-3 w-3" />
                          Re-ingest
                        </KbButton>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 text-[11px] text-ink-muted">
                          <I.Loader className="h-3 w-3 animate-spin" /> running
                        </span>
                      )}
                      <button onClick={() => onOpen(src)} className="rounded-md p-1.5 text-ink-muted hover:bg-bg-muted hover:text-ink">
                        <I.ChevronRight className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---- Sources card view -----------------------------------------------------
function SourcesCards({ sources, onOpen, onReingest }) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      {sources.map(src => (
        <button
          key={src.id}
          onClick={() => onOpen(src)}
          className="group rounded-xl border border-line bg-bg-surface p-4 text-left shadow-card transition-all hover:shadow-cardHover hover:-translate-y-0.5"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-ink-muted">
                <ConnectorChip connectorId={src.connector} />
                {src.kbTarget === "internal" ? <I.Lock className="h-3 w-3" /> : <I.Globe className="h-3 w-3" />}
              </div>
              <div className="mt-1 truncate text-sm font-semibold text-ink">{prettyUrl(src.url)}</div>
            </div>
            <SourceStatusBadge status={src.status} />
          </div>
          <div className="mt-3"><MiniPhaseTrack source={src} /></div>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            <Metric label="Files"     value={window.kbFmtNum(src.files || 0)} accent={src.files > 0 ? "ok" : null} />
            <Metric label="Last sync" value={src.lastRun ? window.kbFmtRel(src.lastRun.at) : "—"} />
            <Metric label="Runs"      value={src.runs?.length || 0} />
          </div>
          <div className="mt-3 flex items-center justify-between text-[11px]">
            <span className="text-ink-muted">Added {window.kbFmtRel(src.addedAt)}</span>
            {src.status === "idle"
              ? <span onClick={(e) => { e.stopPropagation(); onReingest(src); }} className="inline-flex cursor-pointer items-center gap-1 font-medium text-brand hover:underline">
                  <I.RefreshCw className="h-3 w-3" /> Re-ingest
                </span>
              : <span className="font-medium text-ink-soft group-hover:text-brand">Open →</span>}
          </div>
        </button>
      ))}
    </div>
  );
}

function Metric({ label, value, accent }) {
  const c = accent === "ok" ? "text-status-ok" : accent === "info" ? "text-status-info" : "text-ink";
  return (
    <div className="rounded-lg bg-bg-muted px-2 py-2">
      <div className={cn("text-sm font-semibold tabular-nums", c)}>{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-ink-muted">{label}</div>
    </div>
  );
}

// ---- List page -------------------------------------------------------------
function ListPage({ filters, setFilters, onOpenSource, onReingest, onAdd, density, viewMode }) {
  const [search, setSearch] = useState_L("");
  const all = window.KB_SOURCES;

  const filtered = useMemo_L(() => {
    return all
      .filter(s => {
        if (filters.status === "all") return true;
        if (filters.status === "running") return ["discovering", "extracting", "qa"].includes(s.status);
        return s.status === filters.status;
      })
      .filter(s => filters.connector === "all" || s.connector === filters.connector)
      .filter(s => filters.kbTarget === "all" || s.kbTarget === filters.kbTarget)
      .filter(s => filters.origin === "all"
        || (filters.origin === "manual"     && !s.discoveredFrom)
        || (filters.origin === "discovered" && s.discoveredFrom))
      .filter(s => !search.trim() || s.url.toLowerCase().includes(search.toLowerCase()));
  }, [all, filters, search]);

  const counts = useMemo_L(() => {
    const c = { all: all.length, running: 0, queued: 0, idle: 0, failed: 0, needsReview: 0,
                byConnector: {}, byKb: {}, byOrigin: { manual: 0, discovered: 0 } };
    for (const s of all) {
      if (["discovering", "extracting", "qa"].includes(s.status)) c.running++;
      if (s.status === "queued") c.queued++;
      if (s.status === "idle") c.idle++;
      if (s.status === "failed") c.failed++;
      if (s.status === "needs_review") c.needsReview++;
      c.byConnector[s.connector] = (c.byConnector[s.connector] || 0) + 1;
      c.byKb[s.kbTarget] = (c.byKb[s.kbTarget] || 0) + 1;
      if (s.discoveredFrom) c.byOrigin.discovered++; else c.byOrigin.manual++;
    }
    return c;
  }, [all]);

  // Expose counts to filter rail
  window.__kbCounts = counts;

  const totalFiles = all.reduce((a, s) => a + (s.files || 0), 0);

  return (
    <div className="anim-fade-in">
      <div className="mb-5 flex items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
            <I.Database className="h-3.5 w-3.5" />
            <span>Knowledge Base</span>
          </div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink">Sources</h1>
          <p className="mt-1 max-w-2xl text-sm text-ink-muted">
            Every URL feeding the knowledge base. Discovery surfaces new sources as siblings — there are no parent/child relationships and no separate jobs.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <ListKpi icon={I.Database} label="Total sources"  value={counts.all}     hint={`${counts.byOrigin.manual} added, ${counts.byOrigin.discovered} discovered`} tone="neutral" />
        <ListKpi icon={I.Cpu}      label="Currently running" value={counts.running} hint={`${counts.queued} queued`} tone="info" />
        <ListKpi icon={I.FileText} label="Files in KB"    value={window.kbFmtNum(totalFiles)} hint="from these sources" tone="ok" />
        <ListKpi icon={I.AlertTriangle} label="Need attention" value={counts.failed + counts.needsReview} hint={`${counts.failed} failed · ${counts.needsReview} review`} tone="warn" />
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
          {window.kbFmtNum(filtered.length)} of {window.kbFmtNum(counts.all)} sources
        </div>
        <div className="ml-auto flex items-center gap-2">
          <div className="relative">
            <I.Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-faint" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Filter by URL…"
              className="h-8 w-[260px] rounded-lg border border-line bg-bg-surface pl-7 pr-3 text-xs placeholder:text-ink-faint focus:border-ink-faint focus:outline-none"
            />
          </div>
        </div>
      </div>

      <div className="mt-3">
        {viewMode === "cards"
          ? <SourcesCards sources={filtered} onOpen={onOpenSource} onReingest={onReingest} />
          : <SourcesTable sources={filtered} onOpen={onOpenSource} onReingest={onReingest} density={density} />}
      </div>
    </div>
  );
}

Object.assign(window, { ListPage, prettyUrl, SourceStatusBadge });
