// Source detail page — adapts to status: idle / queued / running / failed / needs_review.
// Hero is "what's happening right now", run history sits below.

const { useState: useState_D, useEffect: useEffect_D, useMemo: useMemo_D, useRef: useRef_D } = React;

// ---- Phase track -----------------------------------------------------------
function PhaseTrack({ source }) {
  const phase = window.kbStatusToPhase(source.status);
  const idx = window.kbPhaseIndex(phase);
  const isFailed = source.status === "failed";
  const isIdle = source.status === "idle";
  const phases = window.KB_PHASES;

  return (
    <div className="rounded-xl border border-line bg-bg-surface p-5 shadow-card">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Pipeline</div>
          <div className="mt-1 text-sm text-ink-soft">
            {isFailed ? <span className="text-status-err">Failed during {phases[idx]?.label || "—"}</span> :
             isIdle ? "Up to date — last sync " + window.kbFmtRel(source.lastRun?.at) :
             source.status === "queued" ? `Queued — position ${source.queuePos || 1}` :
             <>Running — <span className="font-semibold text-ink">{phases[idx].label}</span></>}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[11px] uppercase tracking-wide text-ink-muted">Progress</div>
          <div className="text-2xl font-semibold tabular-nums text-ink">{source.progress || 0}%</div>
        </div>
      </div>

      <div className="relative">
        <div className="absolute left-0 right-0 top-5 h-0.5 bg-line" />
        <div
          className={cn("absolute left-0 top-5 h-0.5 transition-all",
            isFailed ? "bg-status-err" : isIdle ? "bg-status-ok" : "bg-status-info")}
          style={{ width: `${(idx / (phases.length - 1)) * 100}%` }}
        />
        <div className="relative grid" style={{ gridTemplateColumns: `repeat(${phases.length}, minmax(0,1fr))` }}>
          {phases.map((p, i) => {
            const past = i < idx;
            const current = i === idx && !isFailed && !isIdle;
            const done = isIdle || past;
            const failed = isFailed && i === idx;

            const ring = failed ? "bg-status-err text-white"
              : done ? "bg-status-ok text-white"
              : current ? "bg-status-info text-white pulse-ring"
              : "bg-bg-surface text-ink-faint border-2 border-line";

            return (
              <div key={p.id} className="flex flex-col items-center gap-2">
                <div className={cn("z-10 grid h-10 w-10 place-items-center rounded-full text-sm font-semibold transition-all", ring)}>
                  {failed ? <I.X className="h-4 w-4" /> :
                   done ? <I.Check className="h-4 w-4" /> :
                   current ? <I.Loader className="h-4 w-4 animate-spin" /> :
                   <span>{i + 1}</span>}
                </div>
                <div className="text-center">
                  <div className={cn("text-xs font-semibold",
                    failed ? "text-status-err" : done ? "text-status-ok" : current ? "text-status-info" : "text-ink-faint")}>
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

// ---- Stat strip (current run while running, last run when idle) ------------
function StatStrip({ source }) {
  const r = source.currentRun || source.lastRun || {};
  const isQueued = source.status === "queued";
  const stats = [
    { label: "Discovered",     value: isQueued ? "—" : window.kbFmtNum(r.discovered) },
    { label: "Extracted",      value: isQueued ? "—" : window.kbFmtNum(r.extracted) },
    { label: "QA passed",      value: isQueued ? "—" : window.kbFmtNum(r.qaPassed) },
    { label: "Files created",  value: isQueued ? "—" : (r.created  ?? 0), tone: "ok" },
    { label: "Files replaced", value: isQueued ? "—" : (r.replaced ?? 0), tone: "info" },
  ];
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line shadow-card sm:grid-cols-5">
      {stats.map(s => (
        <div key={s.label} className="bg-bg-surface px-4 py-3">
          <div className="text-[11px] font-medium uppercase tracking-wide text-ink-muted">{s.label}</div>
          <div className={cn("mt-0.5 text-xl font-semibold tabular-nums",
            s.tone === "ok" ? "text-status-ok" : s.tone === "info" ? "text-status-info" : "text-ink")}>
            {s.value ?? "—"}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---- Activity stream -------------------------------------------------------
function activityMeta(kind) {
  switch (kind) {
    case "discover": return { icon: I.Compass,        bg: "bg-status-infoSoft",    fg: "text-status-info" };
    case "extract":  return { icon: I.FileText,       bg: "bg-status-okSoft",      fg: "text-status-ok" };
    case "image":    return { icon: I.Layers,         bg: "bg-status-infoSoft",    fg: "text-status-info" };
    case "warn":     return { icon: I.AlertTriangle,  bg: "bg-status-warnSoft",    fg: "text-status-warn" };
    case "dedupe":   return { icon: I.FileEdit,       bg: "bg-status-warnSoft",    fg: "text-status-warn" };
    case "qa_pass":  return { icon: I.CheckCircle,    bg: "bg-status-okSoft",      fg: "text-status-ok" };
    case "qa_fail":  return { icon: I.XCircle,        bg: "bg-status-errSoft",     fg: "text-status-err" };
    case "summary":  return { icon: I.Sparkles,       bg: "bg-bg-muted",           fg: "text-ink-soft" };
    default:         return { icon: I.Activity,       bg: "bg-bg-muted",           fg: "text-ink-soft" };
  }
}

function PhaseHeading({ phaseId, count, isCurrent, isDone }) {
  const labels = {
    discovering: { title: "Discovery",      sub: "Finding pages and adding sibling sources" },
    extracting:  { title: "Extracting",     sub: "Reading content and images from each page" },
    qa:          { title: "Quality checks", sub: "Verifying clarity, completeness and uniqueness" },
  };
  const meta = labels[phaseId] || { title: phaseId, sub: "" };
  return (
    <div className="sticky top-0 z-10 -mx-4 mb-2 mt-1 flex items-center justify-between gap-3 border-b border-line bg-bg-surface/95 px-4 py-2 backdrop-blur first:mt-0">
      <div className="flex items-center gap-2.5">
        <div className={cn("grid h-6 w-6 place-items-center rounded-full text-[11px] font-semibold",
          isDone ? "bg-status-ok text-white" :
          isCurrent ? "bg-status-info text-white" : "bg-bg-muted text-ink-muted")}>
          {isDone ? <I.Check className="h-3.5 w-3.5" /> :
           isCurrent ? <I.Loader className="h-3.5 w-3.5 animate-spin" /> :
           <I.Clock className="h-3.5 w-3.5" />}
        </div>
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-ink">{meta.title}</div>
          <div className="text-[11px] text-ink-muted">{meta.sub}</div>
        </div>
      </div>
      <div className="text-[11px] tabular-nums text-ink-muted">{count} {count === 1 ? "activity" : "activities"}</div>
    </div>
  );
}

function ActivityRow({ ev }) {
  const meta = activityMeta(ev.kind);
  const Icon = meta.icon;
  const isSummary = ev.kind === "summary";
  return (
    <div className="anim-stream-in flex items-start gap-3 py-2">
      <div className={cn("mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg", meta.bg)}>
        <Icon className={cn("h-3.5 w-3.5", meta.fg)} />
      </div>
      <div className="min-w-0 flex-1">
        <div className={cn("text-sm leading-tight", isSummary ? "font-semibold text-ink" : "text-ink")}>{ev.title}</div>
        {ev.detail && <div className="mt-0.5 text-xs text-ink-muted">{ev.detail}</div>}
        {ev.url && (
          <div className="mt-1 inline-flex max-w-full items-center gap-1 truncate rounded-md bg-bg-muted px-1.5 py-0.5 font-mono text-[10.5px] text-ink-soft">
            <I.ExternalLink className="h-2.5 w-2.5 shrink-0 text-ink-faint" />
            <span className="truncate">{ev.url}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function LiveStream({ source, paused, onTogglePause }) {
  const [now, setNow] = useState_D(Date.now());
  const startRef = useRef_D(source.currentRun?.startedAt || Date.now());
  const [showRaw, setShowRaw] = useState_D(false);
  const events = window.KB_STREAM_TEMPLATE;
  const containerRef = useRef_D(null);

  const isRunning = ["discovering", "extracting", "qa"].includes(source.status);

  useEffect_D(() => {
    if (paused || !isRunning) return;
    const id = setInterval(() => setNow(Date.now()), 700);
    return () => clearInterval(id);
  }, [paused, isRunning]);

  const totalMs = events[events.length - 1].ts;
  const elapsed = !isRunning
    ? totalMs
    : Math.min(totalMs, totalMs * ((source.progress || 0) / 100) + (paused ? 0 : ((now - startRef.current) % 8000) / 8000 * 1500));

  const visible = events.filter(e => e.ts <= elapsed);

  const phaseOrder = ["discovering", "extracting", "qa"];
  const grouped = phaseOrder
    .map(p => ({ phase: p, items: visible.filter(e => e.phase === p) }))
    .filter(g => g.items.length > 0);

  const currentPhase = window.kbStatusToPhase(source.status);
  const currentIdx = phaseOrder.indexOf(currentPhase);

  useEffect_D(() => {
    if (containerRef.current) containerRef.current.scrollTop = containerRef.current.scrollHeight;
  }, [visible.length]);

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-bg-surface shadow-card">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="grid h-7 w-7 place-items-center rounded-lg bg-status-infoSoft text-status-info">
            <I.Activity className="h-3.5 w-3.5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-ink">Activity</span>
              {isRunning && !paused && (
                <span className="inline-flex items-center gap-1 rounded-full bg-status-infoSoft px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-status-info">
                  <span className="relative flex h-1.5 w-1.5">
                    <span className="absolute inset-0 animate-ping rounded-full bg-status-info opacity-75" />
                    <span className="relative h-1.5 w-1.5 rounded-full bg-status-info" />
                  </span>
                  Live
                </span>
              )}
            </div>
            <div className="text-[11px] text-ink-muted">
              {visible.length} {visible.length === 1 ? "update" : "updates"} · live stream from the ingestion worker
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => setShowRaw(r => !r)} className={cn("inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium",
              showRaw ? "bg-bg-muted text-ink" : "text-ink-muted hover:bg-bg-muted hover:text-ink")}>
            <I.Hash className="h-3 w-3" /> Raw
          </button>
          <button onClick={onTogglePause} disabled={!isRunning}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-ink-muted hover:bg-bg-muted hover:text-ink disabled:opacity-40">
            {paused ? <I.Play className="h-3 w-3" /> : <I.Pause className="h-3 w-3" />}
            {paused ? "Resume" : "Pause"}
          </button>
        </div>
      </div>

      <div ref={containerRef} className="max-h-[420px] overflow-y-auto px-4 pt-2 pb-4 scrollbar-thin">
        {visible.length === 0 ? (
          <div className="flex items-center gap-2 py-10 text-xs text-ink-muted">
            <I.Loader className="h-3.5 w-3.5 animate-spin" /> Waiting for the worker to start streaming activity…
          </div>
        ) : showRaw ? (
          <div className="space-y-1 py-2 font-mono text-[11px] text-ink-soft">
            {visible.map((ev, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="w-12 shrink-0 tabular-nums text-ink-faint">{(ev.ts / 1000).toFixed(2)}s</span>
                <span className="rounded bg-bg-muted px-1.5 py-0.5 text-[10px] font-semibold uppercase text-ink-muted">{ev.phase}</span>
                <span className="text-ink-muted">{ev.kind}</span>
                <span className="min-w-0 flex-1 truncate">{ev.title}{ev.url ? ` — ${ev.url}` : ""}</span>
              </div>
            ))}
          </div>
        ) : (
          <div>
            {grouped.map((g, gi) => {
              const gIdx = phaseOrder.indexOf(g.phase);
              const isCurrent = g.phase === currentPhase && isRunning;
              const isDone = !isRunning || gIdx < currentIdx;
              return (
                <div key={g.phase} className={gi > 0 ? "mt-2" : ""}>
                  <PhaseHeading phaseId={g.phase} count={g.items.length} isCurrent={isCurrent} isDone={isDone} />
                  <div className="divide-y divide-line-soft">
                    {g.items.map((ev, i) => <ActivityRow key={i} ev={ev} />)}
                  </div>
                </div>
              );
            })}
            {isRunning && !paused && (
              <div className="mt-2 flex items-center gap-2 border-t border-line-soft pt-3 text-[11px] text-ink-muted">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inset-0 animate-ping rounded-full bg-status-info opacity-75" />
                  <span className="relative h-1.5 w-1.5 rounded-full bg-status-info" />
                </span>
                Worker is working on the next page…
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ---- Queued view -----------------------------------------------------------
function QueuedView({ source, onCancel }) {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div className="lg:col-span-2 overflow-hidden rounded-xl border border-line bg-bg-surface shadow-card">
        <div className="relative h-1.5 w-full bg-line"><div className="absolute inset-0 barber" /></div>
        <div className="flex items-center justify-center p-10">
          <div className="text-center">
            <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-status-warnSoft text-status-warn">
              <I.Clock className="h-8 w-8" />
            </div>
            <div className="mt-4 text-lg font-semibold text-ink">Waiting for a worker</div>
            <div className="mt-1 text-sm text-ink-muted">
              No worker is available yet. This source is <span className="font-semibold text-ink">position {source.queuePos || 1}</span> in the queue.
            </div>
            <div className="mt-6 inline-flex items-center gap-1.5 rounded-full border border-line bg-bg-muted px-3 py-1 text-[11px] uppercase tracking-wider text-ink-muted">
              <I.Cpu className="h-3 w-3" /> Workers: 4 active · 0 idle
            </div>
            <div className="mt-6 flex justify-center gap-2">
              <KbButton variant="outline" size="md"><I.ArrowUpRight className="h-4 w-4" /> Bump priority</KbButton>
              <KbButton variant="ghost" size="md" onClick={onCancel}><I.X className="h-4 w-4" /> Cancel</KbButton>
            </div>
          </div>
        </div>
      </div>
      <KbCard className="p-4">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Queue ahead of you</div>
        <ol className="mt-3 space-y-2 text-sm">
          {[
            { pos: 1, url: "publish.budget.com/help/cars-and-services", you: source.queuePos === 1 },
            { pos: 2, url: "publish.budget.com/products/budget-fastbreak", you: source.queuePos === 2 },
          ].map((q, i) => (
            <li key={i} className={cn("flex items-center gap-3 rounded-lg border px-3 py-2",
              q.you ? "border-brand/40 bg-brand-soft/40" : "border-line bg-bg")}>
              <span className="grid h-6 w-6 place-items-center rounded-full bg-bg-surface text-[11px] font-semibold text-ink-soft">{q.pos}</span>
              <span className="min-w-0 flex-1 truncate text-xs text-ink-soft">{q.url}</span>
              {q.you && <span className="text-[10px] font-bold uppercase text-brand">you</span>}
            </li>
          ))}
        </ol>
        <div className="mt-3 border-t border-line pt-3 text-[11px] text-ink-muted">
          Estimated start: <span className="font-semibold text-ink">~3 min</span> based on average phase time.
        </div>
      </KbCard>
    </div>
  );
}

// ---- Manifest (idle source — last run output) ------------------------------
function ManifestRow({ row }) {
  const meta =
    row.status === "created"  ? { tone: "ok",   icon: <I.FilePlus className="h-3.5 w-3.5" />, label: "Created" } :
    row.status === "replaced" ? { tone: "info", icon: <I.FileEdit className="h-3.5 w-3.5" />, label: "Replaced" } :
                                { tone: "neutral", icon: <I.X className="h-3.5 w-3.5" />, label: "Skipped" };
  return (
    <tr className="hover:bg-bg-muted/60">
      <td className="px-4 py-2.5"><KbBadge tone={meta.tone}>{meta.icon} {meta.label}</KbBadge></td>
      <td className="px-4 py-2.5">
        <div className="text-sm text-ink">{row.title}</div>
        <div className="font-mono text-[11px] text-ink-muted">{row.url}</div>
      </td>
      <td className="px-4 py-2.5 text-right text-xs text-ink-muted tabular-nums">{row.bytes}</td>
      <td className="px-4 py-2.5 text-right">
        {row.fileId ? (
          <button className="inline-flex items-center gap-1 text-xs font-medium text-status-info hover:underline">
            Open file <I.ExternalLink className="h-3 w-3" />
          </button>
        ) : <span className="text-xs text-ink-faint">—</span>}
      </td>
    </tr>
  );
}

function IdleView({ source }) {
  const [tab, setTab] = useState_D("all");
  const rows = window.KB_RUN_MANIFEST;
  const counts = {
    created:  rows.filter(r => r.status === "created").length,
    replaced: rows.filter(r => r.status === "replaced").length,
    skipped:  rows.filter(r => r.status === "skipped").length,
  };
  const filtered =
    tab === "created"  ? rows.filter(r => r.status === "created") :
    tab === "replaced" ? rows.filter(r => r.status === "replaced") :
    tab === "skipped"  ? rows.filter(r => r.status === "skipped") : rows;
  const tabs = [
    { id: "all",      label: "All",       count: rows.length },
    { id: "created",  label: "Created",   count: counts.created },
    { id: "replaced", label: "Replaced",  count: counts.replaced },
    { id: "skipped",  label: "Skipped",   count: counts.skipped },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
      <div className="xl:col-span-2">
        <div className="mb-2 flex items-center gap-2">
          <h2 className="text-sm font-semibold text-ink">Files from last sync</h2>
          <span className="text-[11px] text-ink-muted">{window.kbFmtRel(source.lastRun?.at)}</span>
        </div>
        <KbCard className="overflow-hidden">
          <div className="flex items-center gap-1 border-b border-line px-3">
            {tabs.map(t => (
              <button key={t.id} onClick={() => setTab(t.id)} className={cn(
                "relative -mb-px flex items-center gap-2 px-3 py-3 text-xs font-semibold transition-colors",
                tab === t.id ? "text-ink" : "text-ink-muted hover:text-ink")}>
                <span>{t.label}</span>
                <span className="rounded-full bg-bg-muted px-1.5 py-0.5 text-[10px] tabular-nums text-ink-muted">{t.count}</span>
                {tab === t.id && <span className="absolute inset-x-2 -bottom-px h-0.5 rounded bg-brand" />}
              </button>
            ))}
          </div>
          <div className="overflow-x-auto scrollbar-thin">
            <table className="w-full text-sm">
              <thead className="bg-bg-muted text-left text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
                <tr>
                  <th className="px-4 py-2.5">Outcome</th>
                  <th className="px-4 py-2.5">Page</th>
                  <th className="px-4 py-2.5 text-right">Size</th>
                  <th className="px-4 py-2.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {filtered.map((r, i) => <ManifestRow key={i} row={r} />)}
              </tbody>
            </table>
          </div>
        </KbCard>
      </div>

      <div className="space-y-4">
        <KbCard className="p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Last sync</div>
          <div className="mt-3 space-y-2 text-sm">
            <SumRow label="When"     value={window.kbFmtRel(source.lastRun?.at)} />
            <SumRow label="Duration" value={window.kbFmtDuration(source.lastRun?.durationMs)} />
            <SumRow label="Created"  value={<span className="font-semibold text-status-ok">+{source.lastRun?.created || 0}</span>} />
            <SumRow label="Replaced" value={<span className="font-semibold text-status-info">~{source.lastRun?.replaced || 0}</span>} />
            <SumRow label="Skipped"  value={<span className="text-ink-muted">{source.lastRun?.skipped || 0}</span>} />
          </div>
        </KbCard>
        <RunHistoryCard source={source} />
      </div>
    </div>
  );
}

function SumRow({ label, value }) {
  return (
    <div className="flex items-center justify-between border-b border-line-soft py-1.5 last:border-0">
      <span className="text-xs text-ink-muted">{label}</span>
      <span className="text-sm text-ink">{value}</span>
    </div>
  );
}

// ---- Run history (compact) -------------------------------------------------
function RunHistoryCard({ source }) {
  if (!source.runs || source.runs.length === 0) {
    return (
      <KbCard className="p-4">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Run history</div>
        <div className="mt-3 text-xs text-ink-muted">No prior runs yet.</div>
      </KbCard>
    );
  }
  return (
    <KbCard className="p-4">
      <div className="flex items-center justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Run history</div>
        <span className="text-[11px] tabular-nums text-ink-muted">{source.runs.length} runs</span>
      </div>
      <ol className="mt-3 space-y-2">
        {source.runs.map((r, i) => (
          <li key={i} className="flex items-center gap-3 rounded-lg border border-line-soft bg-bg-muted/40 px-3 py-2">
            <span className={cn("h-2 w-2 shrink-0 rounded-full",
              r.status === "failed" ? "bg-status-err" : "bg-status-ok")} />
            <div className="min-w-0 flex-1">
              <div className="text-xs font-medium text-ink">{window.kbFmtRel(r.at)}</div>
              <div className="text-[10.5px] text-ink-muted">
                {r.status === "failed"
                  ? <span className="text-status-err">{r.error || "failed"}</span>
                  : <>+{r.created} · ~{r.replaced} · {window.kbFmtDuration(r.durationMs)}</>}
              </div>
            </div>
            <span className="text-[10px] text-ink-faint">by {r.by}</span>
          </li>
        ))}
      </ol>
    </KbCard>
  );
}

// ---- Failed view -----------------------------------------------------------
function FailedView({ source }) {
  return (
    <KbCard className="border-status-err/30 bg-status-errSoft/40">
      <div className="p-5">
        <div className="flex items-start gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-status-err text-white">
            <I.XCircle className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-status-err">Last ingestion failed</div>
            <div className="mt-1 text-sm text-ink">{source.lastRun?.error || "Unknown error during ingestion."}</div>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <KbButton variant="primary" size="sm"><I.RefreshCw className="h-3.5 w-3.5" /> Retry now</KbButton>
              <KbButton variant="outline" size="sm"><I.Settings className="h-3.5 w-3.5" /> Edit credentials</KbButton>
              <KbButton variant="ghost" size="sm"><I.ExternalLink className="h-3.5 w-3.5" /> View error logs</KbButton>
            </div>
          </div>
        </div>
      </div>
    </KbCard>
  );
}

// ---- Discovered siblings panel (running source) ----------------------------
function DiscoveredSiblings({ parentId }) {
  const siblings = window.KB_SOURCES.filter(s => s.discoveredFrom === parentId);
  return (
    <KbCard className="p-4">
      <div className="flex items-center justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Discovered as siblings</div>
        <span className="text-[11px] tabular-nums text-ink-muted">{siblings.length}</span>
      </div>
      <div className="mt-3 space-y-1.5 text-xs">
        {siblings.length === 0 && <div className="text-ink-muted">No new sources discovered yet.</div>}
        {siblings.map(s => (
          <div key={s.id} className="flex items-center gap-2 rounded-lg border border-line-soft bg-bg-muted/40 px-2 py-1.5">
            {s.status === "needs_review"
              ? <I.AlertTriangle className="h-3 w-3 shrink-0 text-status-warn" />
              : <I.CheckCircle className="h-3 w-3 shrink-0 text-status-ok" />}
            <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-ink-soft">{prettyUrl(s.url)}</span>
          </div>
        ))}
      </div>
      <div className="mt-2 text-[10.5px] text-ink-faint">
        New sources are added to your sources list. Each can be ingested independently.
      </div>
    </KbCard>
  );
}

// ---- Detail page -----------------------------------------------------------
function DetailPage({ source, onBack, jobDetailStyle }) {
  const [paused, setPaused] = useState_D(false);
  if (!source) return null;

  const connector = window.KB_CONNECTORS.find(c => c.id === source.connector);

  const isQueued = source.status === "queued";
  const isFailed = source.status === "failed";
  const isIdle = source.status === "idle";
  const isRunning = ["discovering", "extracting", "qa"].includes(source.status);
  const isNeedsReview = source.status === "needs_review";

  const discoveredFrom = source.discoveredFrom ? window.KB_SOURCES.find(s => s.id === source.discoveredFrom) : null;

  return (
    <div className="anim-fade-in space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <button onClick={onBack} className="mb-2 inline-flex items-center gap-1 text-xs font-medium text-ink-muted hover:text-ink">
            <I.ArrowLeft className="h-3.5 w-3.5" /> Back to sources
          </button>
          <div className="flex flex-wrap items-center gap-3">
            <SourceStatusBadge status={source.status} />
            <div className="flex items-center gap-1.5 text-[11px] text-ink-muted">
              <span className="grid h-4 w-4 place-items-center rounded text-[9px] font-bold text-white" style={{ background: connector?.color }}>
                {connector?.label.slice(0, 1)}
              </span>
              <span>{connector?.fullName}</span>
            </div>
            <div className="flex items-center gap-1.5 text-[11px] text-ink-muted">
              {source.kbTarget === "internal" ? <I.Lock className="h-3 w-3" /> : <I.Globe className="h-3 w-3" />}
              <span className="capitalize">{source.kbTarget} KB</span>
            </div>
            <div className="flex items-center gap-1.5 text-[11px] text-ink-muted">
              <I.User className="h-3 w-3" /> Added by {(source.addedBy || "").split("@")[0]}
            </div>
            {source.workerId && (
              <div className="flex items-center gap-1.5 text-[11px] text-ink-muted">
                <I.Cpu className="h-3 w-3" /> Worker #{source.workerId}
              </div>
            )}
          </div>
          <h1 className="mt-2 break-all text-2xl font-semibold text-ink">{prettyUrl(source.url)}</h1>
          {discoveredFrom && (
            <div className="mt-1.5 inline-flex items-center gap-1.5 text-xs text-ink-muted">
              <I.Compass className="h-3 w-3" />
              Discovered from
              <button className="font-medium text-ink-soft hover:text-brand hover:underline">
                {prettyUrl(discoveredFrom.url)}
              </button>
            </div>
          )}
          {source.steeringPrompt && (
            <div className="mt-3 inline-flex items-start gap-2 rounded-lg border border-line bg-bg-muted px-3 py-2 text-xs text-ink-soft">
              <I.Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-status-info" />
              <span><span className="font-semibold">Steering: </span>{source.steeringPrompt}</span>
            </div>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {isRunning && <KbButton variant="ghost" size="md"><I.StopCircle className="h-4 w-4" /> Cancel</KbButton>}
          {(isIdle || isFailed || isNeedsReview) && (
            <KbButton variant="primary" size="md"><I.RefreshCw className="h-4 w-4" /> {isFailed ? "Retry" : "Re-ingest"}</KbButton>
          )}
          <KbButton variant="outline" size="md"><I.ExternalLink className="h-4 w-4" /> Open URL</KbButton>
        </div>
      </div>

      {/* Pipeline */}
      {!isQueued && !isNeedsReview && <PhaseTrack source={source} />}
      {!isQueued && !isNeedsReview && <StatStrip source={source} />}

      {/* Body */}
      {isQueued && <QueuedView source={source} onCancel={onBack} />}
      {isNeedsReview && (
        <KbCard className="border-status-warn/30 bg-status-warnSoft/30 p-5">
          <div className="flex items-start gap-3">
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-status-warn text-white">
              <I.AlertTriangle className="h-5 w-5" />
            </div>
            <div className="flex-1">
              <div className="text-sm font-semibold text-status-warn">This source was discovered but flagged uncertain</div>
              <div className="mt-1 text-sm text-ink">It looks related to <span className="font-medium">{prettyUrl(discoveredFrom?.url || "")}</span> but the system wasn't confident enough to ingest automatically.</div>
              <div className="mt-4 flex items-center gap-2">
                <KbButton variant="primary" size="sm"><I.Zap className="h-3.5 w-3.5" /> Approve & ingest</KbButton>
                <KbButton variant="outline" size="sm"><I.X className="h-3.5 w-3.5" /> Discard</KbButton>
              </div>
            </div>
          </div>
        </KbCard>
      )}

      {isRunning && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <div className={cn(jobDetailStyle === "summary" ? "xl:col-span-1" : "xl:col-span-2")}>
            <LiveStream source={source} paused={paused} onTogglePause={() => setPaused(p => !p)} />
          </div>
          <div className={cn("space-y-4", jobDetailStyle === "summary" ? "xl:col-span-2" : "xl:col-span-1")}>
            <DiscoveredSiblings parentId={source.id} />
            <RunHistoryCard source={source} />
          </div>
        </div>
      )}

      {isIdle && <IdleView source={source} />}

      {isFailed && (
        <>
          <FailedView source={source} />
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <div className="xl:col-span-2">
              <LiveStream source={{ ...source, progress: 47, status: "extracting" }} paused={true} onTogglePause={() => {}} />
            </div>
            <RunHistoryCard source={source} />
          </div>
        </>
      )}
    </div>
  );
}

Object.assign(window, { DetailPage });
