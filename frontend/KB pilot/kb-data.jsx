// Mock data — flat sources, no jobs.
// A source IS the unit. State lives on it directly.

const NOW = Date.now();
const m = (n) => n * 60 * 1000;
const h = (n) => n * 3600 * 1000;
const d = (n) => n * 86400 * 1000;

const CONNECTORS = [
  { id: "aem",        label: "AEM",        fullName: "Adobe Experience Manager", enabled: true,  color: "#2563EB", description: "Public website + internal authoring pages" },
  { id: "helpcms",    label: "HelpCMS",    fullName: "Help Center CMS",          enabled: false, color: "#9333EA", description: "Salesforce-backed customer help articles" },
  { id: "magnolia",   label: "Magnolia",   fullName: "Magnolia DX Platform",     enabled: false, color: "#0EA5E9", description: "Loyalty + corporate microsites" },
  { id: "confluence", label: "Confluence", fullName: "Atlassian Confluence",     enabled: false, color: "#0891B2", description: "Internal team knowledge wikis" },
];

// status: idle | queued | discovering | extracting | qa | failed
// (no "completed" — that's just idle with a successful last_run)
const SOURCES = [
  {
    id: "src_8f21c",
    url: "https://author.abgi.com/agent-portal/policies",
    connector: "aem",
    kbTarget: "internal",
    status: "extracting",
    progress: 58,
    workerId: 3,
    addedAt: NOW - d(7),
    addedBy: "j.morales@abgi.com",
    discoveredFrom: null,
    steeringPrompt: "Focus on rental policies, fees, age restrictions",
    files: 19,
    currentRun: { startedAt: NOW - m(2), discovered: 42, extracted: 24, qaPassed: 19, created: 14, replaced: 5 },
    lastRun: { at: NOW - h(5), durationMs: m(22), status: "success", created: 87, replaced: 32, skipped: 5 },
    runs: [
      { at: NOW - h(5),       durationMs: m(22), status: "success", created: 87, replaced: 32, skipped: 5,  by: "j.morales" },
      { at: NOW - d(2) - h(3),durationMs: m(18), status: "success", created: 11, replaced: 7,  skipped: 0,  by: "ops" },
      { at: NOW - d(5),       durationMs: m(28), status: "success", created: 64, replaced: 12, skipped: 3,  by: "j.morales" },
      { at: NOW - d(7),       durationMs: m(31), status: "success", created: 92, replaced: 0,  skipped: 0,  by: "j.morales" },
    ],
  },
  {
    id: "src_3c91a",
    url: "https://author.abgi.com/agent-portal/loyalty",
    connector: "aem",
    kbTarget: "internal",
    status: "discovering",
    progress: 22,
    workerId: 1,
    addedAt: NOW - d(3),
    addedBy: "k.chen@abgi.com",
    discoveredFrom: null,
    steeringPrompt: null,
    files: 0,
    currentRun: { startedAt: NOW - m(6), discovered: 18, extracted: 0, qaPassed: 0, created: 0, replaced: 0 },
    lastRun: null,
    runs: [],
  },
  {
    id: "src_a92e0",
    url: "https://publish.budget.com/en/help/cars-and-services",
    connector: "aem",
    kbTarget: "public",
    status: "queued",
    progress: 0,
    workerId: null,
    queuePos: 1,
    addedAt: NOW - m(4),
    addedBy: "j.morales@abgi.com",
    discoveredFrom: null,
    steeringPrompt: null,
    files: 0,
    currentRun: null,
    lastRun: null,
    runs: [],
  },
  {
    id: "src_b71f5",
    url: "https://publish.budget.com/en/products/budget-fastbreak",
    connector: "aem",
    kbTarget: "public",
    status: "queued",
    progress: 0,
    workerId: null,
    queuePos: 2,
    addedAt: NOW - m(8),
    addedBy: "ops@abgi.com",
    discoveredFrom: null,
    steeringPrompt: null,
    files: 0,
    currentRun: null,
    lastRun: null,
    runs: [],
  },
  {
    id: "src_6d4b2",
    url: "https://publish.avis.com/en/help",
    connector: "aem",
    kbTarget: "public",
    status: "idle",
    progress: 100,
    workerId: null,
    addedAt: NOW - d(14),
    addedBy: "k.chen@abgi.com",
    discoveredFrom: null,
    steeringPrompt: null,
    files: 51,
    currentRun: null,
    lastRun: { at: NOW - h(2), durationMs: m(11), status: "success", created: 38, replaced: 13, skipped: 5, discovered: 56 },
    runs: [
      { at: NOW - h(2),  durationMs: m(11), status: "success", created: 38, replaced: 13, skipped: 5, by: "k.chen" },
      { at: NOW - d(2),  durationMs: m(9),  status: "success", created: 4,  replaced: 8,  skipped: 1, by: "ops" },
      { at: NOW - d(5),  durationMs: m(12), status: "success", created: 51, replaced: 0,  skipped: 0, by: "k.chen" },
    ],
  },
  {
    id: "src_5fa83",
    url: "https://publish.payless.com/en/help",
    connector: "aem",
    kbTarget: "public",
    status: "failed",
    progress: 47,
    workerId: null,
    addedAt: NOW - d(2) - h(5),
    addedBy: "ops@abgi.com",
    discoveredFrom: null,
    steeringPrompt: null,
    files: 0,
    currentRun: null,
    lastRun: { at: NOW - d(1) - h(3), durationMs: m(7), status: "failed", error: "Authentication failed: connector credentials expired (HTTP 401)" },
    runs: [
      { at: NOW - d(1) - h(3), durationMs: m(7), status: "failed", error: "HTTP 401", by: "ops" },
    ],
  },
  {
    id: "src_4ab72",
    url: "https://publish.avis.com/en/products/preferred",
    connector: "aem",
    kbTarget: "public",
    status: "idle",
    progress: 100,
    workerId: null,
    addedAt: NOW - d(20),
    addedBy: "k.chen@abgi.com",
    discoveredFrom: null,
    steeringPrompt: null,
    files: 18,
    currentRun: null,
    lastRun: { at: NOW - d(2), durationMs: m(14), status: "success", created: 11, replaced: 7, skipped: 0 },
    runs: [
      { at: NOW - d(2),  durationMs: m(14), status: "success", created: 11, replaced: 7, skipped: 0, by: "k.chen" },
      { at: NOW - d(9),  durationMs: m(13), status: "success", created: 18, replaced: 0, skipped: 0, by: "k.chen" },
    ],
  },
  // -------- Discovered siblings (provenance via discoveredFrom) --------
  {
    id: "src_d_001",
    url: "https://author.abgi.com/agent-portal/policies/age-requirements",
    connector: "aem",
    kbTarget: "internal",
    status: "needs_review",
    progress: 0,
    addedAt: NOW - m(1),
    addedBy: "system",
    discoveredFrom: "src_8f21c",
    steeringPrompt: null,
    files: 0,
    currentRun: null,
    lastRun: null,
    runs: [],
  },
  {
    id: "src_d_002",
    url: "https://author.abgi.com/agent-portal/policies/young-driver-fee",
    connector: "aem",
    kbTarget: "internal",
    status: "idle",
    progress: 100,
    addedAt: NOW - m(2),
    addedBy: "system",
    discoveredFrom: "src_8f21c",
    steeringPrompt: null,
    files: 1,
    currentRun: null,
    lastRun: { at: NOW - m(1), durationMs: m(1), status: "success", created: 1, replaced: 0, skipped: 0 },
    runs: [{ at: NOW - m(1), durationMs: m(1), status: "success", created: 1, replaced: 0, skipped: 0, by: "system" }],
  },
];

// Activity timeline template (re-used in source detail when running)
const STREAM_TEMPLATE = [
  { ts: 200,  phase: "discovering", kind: "summary",  title: "Discovery started",          detail: "Resolved root URL · robots.txt allows crawl" },
  { ts: 1500, phase: "discovering", kind: "discover", title: "Found page",                  detail: "Age Requirements for Rental",   url: "/policies/age-requirements" },
  { ts: 2200, phase: "discovering", kind: "discover", title: "Found page",                  detail: "Young Driver Fee Schedule",     url: "/policies/young-driver-fee" },
  { ts: 3000, phase: "discovering", kind: "discover", title: "Found page",                  detail: "Cancellation & Refund Policy", url: "/policies/cancellation" },
  { ts: 3700, phase: "discovering", kind: "warn",     title: "Page needs review",           detail: "Could not classify intent confidently", url: "/legal/terms-of-rental" },
  { ts: 4400, phase: "discovering", kind: "summary",  title: "Discovered 42 pages",         detail: "Added as siblings · 1 needs review" },
  { ts: 5000, phase: "extracting", kind: "summary",   title: "Extracting content",          detail: "Reading pages with 3 parallel workers" },
  { ts: 5800, phase: "extracting", kind: "extract",   title: "Read page",                   detail: "Age Requirements for Rental · 1.2 KB",  url: "/policies/age-requirements" },
  { ts: 6600, phase: "extracting", kind: "extract",   title: "Read page",                   detail: "Young Driver Fee Schedule · 0.8 KB",   url: "/policies/young-driver-fee" },
  { ts: 7400, phase: "extracting", kind: "image",     title: "Captured 3 images",           detail: "Hero photos referenced from /policies" },
  { ts: 8100, phase: "extracting", kind: "extract",   title: "Read page",                   detail: "Cancellation & Refund Policy · 2.1 KB", url: "/policies/cancellation" },
  { ts: 8900, phase: "extracting", kind: "warn",      title: "Slow response — retrying",    detail: "Insurance policy page took >10s · attempt 1 of 3", url: "/policies/insurance" },
  { ts: 9700, phase: "extracting", kind: "extract",   title: "Read page",                   detail: "Loss Damage Waiver & Insurance · 3.4 KB", url: "/policies/insurance" },
  { ts: 10500,phase: "qa",         kind: "summary",   title: "Quality & uniqueness checks", detail: "Comparing extracted pages to existing KB" },
  { ts: 11200,phase: "qa",         kind: "qa_pass",   title: "Passed quality check",        detail: "Score 0.94 · clear, complete, on-policy", url: "/policies/age-requirements" },
  { ts: 11900,phase: "qa",         kind: "qa_pass",   title: "Passed quality check",        detail: "Score 0.91 · well-structured fee table",  url: "/policies/young-driver-fee" },
  { ts: 12600,phase: "qa",         kind: "dedupe",    title: "Will replace existing file",  detail: "84% similar to current Cancellation Policy", url: "/policies/cancellation" },
  { ts: 13300,phase: "qa",         kind: "qa_pass",   title: "Passed quality check",        detail: "Score 0.88 · long but coherent",           url: "/policies/insurance" },
  { ts: 14000,phase: "qa",         kind: "summary",   title: "QA complete",                 detail: "19 of 24 will be added · 5 will replace existing files" },
];

// "Files produced" by the most recent successful run on a source (used in detail)
const RUN_MANIFEST = [
  { url: "/policies/age-requirements",    status: "created",  fileId: "f-001", title: "Age Requirements for Rental",     bytes: "1.2 KB" },
  { url: "/policies/young-driver-fee",    status: "created",  fileId: "f-002", title: "Young Driver Fee Schedule",       bytes: "0.8 KB" },
  { url: "/policies/cancellation",        status: "replaced", fileId: "f-003", title: "Cancellation & Refund Policy",    bytes: "2.1 KB" },
  { url: "/policies/insurance",           status: "created",  fileId: "f-004", title: "Loss Damage Waiver & Insurance",  bytes: "3.4 KB" },
  { url: "/policies/late-return",         status: "created",  fileId: "f-005", title: "Late Return & Grace Period",      bytes: "0.9 KB" },
  { url: "/policies/additional-driver",   status: "replaced", fileId: "f-006", title: "Additional Driver Policy",        bytes: "1.1 KB" },
  { url: "/policies/fuel-options",        status: "created",  fileId: "f-007", title: "Fuel Service & Options",          bytes: "1.7 KB" },
  { url: "/policies/duplicate-fees",      status: "skipped",  fileId: null,    title: "Duplicate Fees (skipped: dupe)",  bytes: "—" },
  { url: "/policies/loyalty-discounts",   status: "created",  fileId: "f-008", title: "Loyalty Program Discounts",       bytes: "2.4 KB" },
  { url: "/policies/upgrade-eligibility", status: "created",  fileId: "f-009", title: "Upgrade Eligibility Rules",       bytes: "1.0 KB" },
];

const PHASES = [
  { id: "queued",      label: "Queued",     short: "Queue" },
  { id: "discovering", label: "Discovery",  short: "Discover" },
  { id: "extracting",  label: "Extracting", short: "Extract" },
  { id: "qa",          label: "QA",         short: "QA" },
  { id: "done",        label: "Done",       short: "Done" },
];

function statusToPhase(status) {
  if (status === "queued") return "queued";
  if (status === "discovering") return "discovering";
  if (status === "extracting") return "extracting";
  if (status === "qa") return "qa";
  if (status === "idle") return "done";
  return "done";
}

function phaseIndex(phase) {
  const i = PHASES.findIndex(p => p.id === phase);
  return i < 0 ? 0 : i;
}

function fmtRel(ts) {
  if (!ts) return "—";
  const diff = Date.now() - ts;
  if (diff < 0) return "in " + fmtRel(Date.now() + Math.abs(diff));
  if (diff < 45_000) return "just now";
  const mins = Math.round(diff / 60_000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(diff / 3_600_000);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(diff / 86_400_000);
  if (days < 7) return `${days}d ago`;
  return new Date(ts).toLocaleDateString();
}
function fmtNum(n) { if (n == null) return "—"; return n.toLocaleString(); }
function fmtDuration(ms) {
  if (ms == null || ms < 0) return "—";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const mn = Math.floor(s / 60);
  const sec = s % 60;
  if (mn < 60) return `${mn}m ${sec}s`;
  const hr = Math.floor(mn / 60);
  return `${hr}h ${mn % 60}m`;
}

Object.assign(window, {
  KB_CONNECTORS: CONNECTORS,
  KB_SOURCES: SOURCES,
  KB_STREAM_TEMPLATE: STREAM_TEMPLATE,
  KB_RUN_MANIFEST: RUN_MANIFEST,
  KB_PHASES: PHASES,
  kbStatusToPhase: statusToPhase,
  kbPhaseIndex: phaseIndex,
  kbFmtRel: fmtRel,
  kbFmtNum: fmtNum,
  kbFmtDuration: fmtDuration,
});
