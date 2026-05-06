// Top-level App. Routing between source list and source detail.

const { useState: useState_A, useEffect: useEffect_A } = React;

// ---- New source modal ------------------------------------------------------
function NewSourceModal({ open, onClose }) {
  const [step, setStep] = useState_A(1);
  const [connector, setConnector] = useState_A("aem");
  const [kbTarget, setKbTarget] = useState_A("public");
  const [urls, setUrls] = useState_A("https://publish.budget.com/en/help/cars-and-services\nhttps://publish.budget.com/en/products/budget-fastbreak");
  const [steering, setSteering] = useState_A("");
  const [priority, setPriority] = useState_A("normal");

  useEffect_A(() => { if (open) setStep(1); }, [open]);

  if (!open) return null;
  const urlList = urls.split(/\n+/).map(s => s.trim()).filter(Boolean);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center anim-fade-in">
      <div className="absolute inset-0 bg-ink/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-[640px] max-w-[92vw] overflow-hidden rounded-xl border border-line bg-bg-surface shadow-pop">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <div>
            <div className="text-sm font-semibold text-ink">Add sources</div>
            <div className="mt-0.5 text-xs text-ink-muted">Step {step} of 2 — {step === 1 ? "Connector & target" : "URLs & options"}</div>
          </div>
          <button onClick={onClose} className="rounded-md p-1.5 text-ink-muted hover:bg-bg-muted hover:text-ink">
            <I.X className="h-4 w-4" />
          </button>
        </div>

        {step === 1 && (
          <div className="space-y-5 p-5">
            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">Connector</div>
              <div className="grid grid-cols-2 gap-2">
                {window.KB_CONNECTORS.map(c => (
                  <button key={c.id} disabled={!c.enabled} onClick={() => setConnector(c.id)}
                    className={cn(
                      "flex items-center gap-3 rounded-lg border px-3 py-3 text-left text-sm transition-colors",
                      !c.enabled && "cursor-not-allowed opacity-60",
                      connector === c.id && c.enabled
                        ? "border-brand bg-brand-soft"
                        : "border-line bg-bg-surface hover:bg-bg-muted")}>
                    <span className="grid h-9 w-9 place-items-center rounded-lg text-sm font-bold text-white" style={{ background: c.enabled ? c.color : "#94A3B8" }}>
                      {c.label.slice(0, 1)}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-ink">{c.label}</span>
                        {!c.enabled && <span className="rounded-full border border-line bg-bg-muted px-1.5 py-0.5 text-[9px] font-semibold uppercase text-ink-muted">Soon</span>}
                      </div>
                      <div className="text-[11px] text-ink-muted truncate">{c.fullName}</div>
                    </div>
                    {connector === c.id && c.enabled && <I.Check className="h-4 w-4 text-brand" />}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">KB target</div>
              <div className="grid grid-cols-2 gap-2">
                {[
                  { id: "public",   icon: <I.Globe className="h-4 w-4" />, label: "Public KB",   sub: "Visible to customers" },
                  { id: "internal", icon: <I.Lock  className="h-4 w-4" />, label: "Internal KB", sub: "Agent-only knowledge" },
                ].map(t => (
                  <button key={t.id} onClick={() => setKbTarget(t.id)}
                    className={cn("flex items-start gap-3 rounded-lg border px-3 py-3 text-left",
                      kbTarget === t.id ? "border-brand bg-brand-soft" : "border-line bg-bg-surface hover:bg-bg-muted")}>
                    <div className={cn("grid h-8 w-8 place-items-center rounded-lg",
                      kbTarget === t.id ? "bg-brand text-white" : "bg-bg-muted text-ink-muted")}>{t.icon}</div>
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-ink">{t.label}</div>
                      <div className="text-[11px] text-ink-muted">{t.sub}</div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-5 p-5">
            <div>
              <div className="mb-2 flex items-center justify-between">
                <div className="text-xs font-semibold uppercase tracking-wider text-ink-muted">URLs</div>
                <div className="text-[11px] text-ink-muted tabular-nums">{urlList.length} sources</div>
              </div>
              <textarea value={urls} onChange={e => setUrls(e.target.value)} rows={6}
                className="w-full rounded-lg border border-line bg-bg-surface p-3 font-mono text-xs text-ink placeholder:text-ink-faint focus:border-ink-faint focus:outline-none"
                placeholder="One URL per line" />
              <div className="mt-1 text-[11px] text-ink-muted">Each URL becomes its own source. Discovery may add more siblings during ingestion.</div>
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <div className="text-xs font-semibold uppercase tracking-wider text-ink-muted">Steering prompt <span className="font-normal normal-case text-ink-faint">(optional)</span></div>
                <I.Sparkles className="h-3.5 w-3.5 text-status-info" />
              </div>
              <input value={steering} onChange={e => setSteering(e.target.value)}
                placeholder="e.g. Focus on rental policies, fees, age restrictions"
                className="h-9 w-full rounded-lg border border-line bg-bg-surface px-3 text-sm placeholder:text-ink-faint focus:border-ink-faint focus:outline-none" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">Priority</div>
                <div className="flex items-center gap-1 rounded-lg border border-line bg-bg-muted p-1">
                  {["low", "normal", "high"].map(p => (
                    <button key={p} onClick={() => setPriority(p)}
                      className={cn("flex-1 rounded-md px-2 py-1.5 text-xs font-medium capitalize",
                        priority === p ? "bg-bg-surface text-ink shadow-sm" : "text-ink-muted hover:text-ink")}>{p}</button>
                  ))}
                </div>
              </div>
              <div>
                <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">Schedule</div>
                <button className="flex h-9 w-full items-center justify-between rounded-lg border border-line bg-bg-surface px-3 text-sm text-ink-soft hover:bg-bg-muted">
                  <span>Run immediately</span>
                  <I.ChevronDown className="h-3.5 w-3.5 text-ink-muted" />
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="flex items-center justify-between border-t border-line bg-bg-muted/40 px-5 py-3">
          <div className="text-[11px] text-ink-muted">
            {step === 1 ? `Will add ${urlList.length} source(s)` : `Adding to ${connector.toUpperCase()} → ${kbTarget}`}
          </div>
          <div className="flex items-center gap-2">
            {step === 2 && <KbButton variant="ghost" size="md" onClick={() => setStep(1)}><I.ChevronLeft className="h-4 w-4" /> Back</KbButton>}
            {step === 1 && <KbButton variant="ghost" size="md" onClick={onClose}>Cancel</KbButton>}
            {step === 1 && <KbButton variant="primary" size="md" onClick={() => setStep(2)}>Next <I.ChevronRight className="h-4 w-4" /></KbButton>}
            {step === 2 && <KbButton variant="primary" size="md" onClick={onClose}><I.Play className="h-4 w-4" /> Add {urlList.length} source{urlList.length !== 1 ? "s" : ""}</KbButton>}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---- App -------------------------------------------------------------------
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "density": "comfortable",
  "viewMode": "table",
  "jobDetailStyle": "stream",
  "demoSourceId": "src_8f21c"
}/*EDITMODE-END*/;

function App() {
  const [openSource, setOpenSource] = useState_A(null);
  const [newOpen, setNewOpen] = useState_A(false);
  const [filters, setFilters] = useState_A({ status: "all", connector: "all", kbTarget: "all", origin: "all" });

  const T = window.useTweaks ? window.useTweaks(TWEAK_DEFAULTS) : { tweaks: TWEAK_DEFAULTS, setTweak: () => {} };
  const tweaks = T.tweaks || TWEAK_DEFAULTS;
  const setTweak = T.setTweak || (() => {});

  const handleReingest = (src) => {
    // demo: open the source detail; real backend would kick off a run
    setOpenSource(src);
  };

  const breadcrumbs = openSource
    ? [
        { label: "Knowledge Base", onClick: () => setOpenSource(null) },
        { label: "Sources",        onClick: () => setOpenSource(null) },
        { label: window.prettyUrl ? window.prettyUrl(openSource.url) : openSource.url },
      ]
    : [{ label: "Knowledge Base" }, { label: "Sources" }];

  // Initial counts (so FilterRail has something on first paint before ListPage runs)
  const counts = window.__kbCounts || {
    all: window.KB_SOURCES.length, running: 0, queued: 0, idle: 0, failed: 0, needsReview: 0,
    byConnector: {}, byKb: {}, byOrigin: { manual: 0, discovered: 0 },
  };

  return (
    <div className="flex h-screen overflow-hidden bg-bg">
      <AppSidebar collapsed={false} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onNewIngestion={() => setNewOpen(true)} breadcrumbs={breadcrumbs} />
        <div className="flex flex-1 overflow-hidden">
          {!openSource && (
            <FilterRail filters={filters} setFilters={setFilters} counts={counts} density={tweaks.density} />
          )}
          <main className="flex-1 overflow-y-auto scrollbar-thin">
            <div className="mx-auto max-w-[1400px] p-6">
              {!openSource ? (
                <ListPage
                  filters={filters}
                  setFilters={setFilters}
                  onOpenSource={setOpenSource}
                  onReingest={handleReingest}
                  onAdd={() => setNewOpen(true)}
                  density={tweaks.density}
                  viewMode={tweaks.viewMode}
                />
              ) : (
                <DetailPage
                  source={openSource}
                  onBack={() => setOpenSource(null)}
                  jobDetailStyle={tweaks.jobDetailStyle}
                />
              )}
            </div>
          </main>
        </div>
      </div>

      <NewSourceModal open={newOpen} onClose={() => setNewOpen(false)} />

      {window.TweaksPanel && (
        <window.TweaksPanel title="Tweaks">
          <window.TweakSection title="Layout">
            <window.TweakRadio
              label="Density"
              value={tweaks.density}
              onChange={v => setTweak("density", v)}
              options={[
                { value: "comfortable", label: "Comfy" },
                { value: "compact",     label: "Compact" },
              ]}
            />
            <window.TweakRadio
              label="Sources view"
              value={tweaks.viewMode}
              onChange={v => setTweak("viewMode", v)}
              options={[
                { value: "table", label: "Table" },
                { value: "cards", label: "Cards" },
              ]}
            />
          </window.TweakSection>
          <window.TweakSection title="Source detail">
            <window.TweakRadio
              label="Emphasis"
              value={tweaks.jobDetailStyle}
              onChange={v => setTweak("jobDetailStyle", v)}
              options={[
                { value: "stream",  label: "Stream-first" },
                { value: "summary", label: "Summary-first" },
              ]}
            />
          </window.TweakSection>
          <window.TweakSection title="Demo">
            <window.TweakSelect
              label="Open source state"
              value={tweaks.demoSourceId}
              onChange={v => {
                setTweak("demoSourceId", v);
                const src = window.KB_SOURCES.find(s => s.id === v);
                if (src) setOpenSource(src);
              }}
              options={window.KB_SOURCES.map(s => ({
                value: s.id,
                label: `${s.status.toUpperCase()} — ${window.prettyUrl ? window.prettyUrl(s.url) : s.url}`,
              }))}
            />
            <window.TweakButton onClick={() => setOpenSource(null)}>Back to list</window.TweakButton>
          </window.TweakSection>
        </window.TweaksPanel>
      )}
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
