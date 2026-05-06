// Small reusable UI primitives (Badge, Button, Card, Icon wrapper, Tooltip-light)

const cn = (...xs) => xs.filter(Boolean).join(" ");

// ---- Lucide-like inline icons (24x24 stroke) -------------------------------
// Only what we use. Each accepts {className, size}.
function makeIcon(paths) {
  return function Icon({ className = "h-4 w-4", strokeWidth = 2, ...rest }) {
    return (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={className}
        aria-hidden="true"
        {...rest}
      >
        {paths}
      </svg>
    );
  };
}

const I = {
  Search:    makeIcon(<><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></>),
  Plus:      makeIcon(<><path d="M12 5v14M5 12h14" /></>),
  ChevronDown: makeIcon(<><path d="m6 9 6 6 6-6" /></>),
  ChevronRight: makeIcon(<><path d="m9 6 6 6-6 6" /></>),
  ChevronLeft: makeIcon(<><path d="m15 6-6 6 6 6" /></>),
  Folder:    makeIcon(<><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" /></>),
  Database:  makeIcon(<><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></>),
  Globe:     makeIcon(<><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" /></>),
  Lock:      makeIcon(<><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></>),
  Play:      makeIcon(<><path d="M6 4.5v15l13-7.5z" fill="currentColor" stroke="none" /></>),
  CheckCircle: makeIcon(<><circle cx="12" cy="12" r="9" /><path d="m8 12 3 3 5-6" /></>),
  Check:     makeIcon(<><path d="m5 12 5 5 9-11" /></>),
  X:         makeIcon(<><path d="M18 6 6 18M6 6l12 12" /></>),
  XCircle:   makeIcon(<><circle cx="12" cy="12" r="9" /><path d="m9 9 6 6M15 9l-6 6" /></>),
  AlertTriangle: makeIcon(<><path d="M10.3 3.4 1.7 18a2 2 0 0 0 1.7 3h17.2a2 2 0 0 0 1.7-3L13.7 3.4a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4M12 17h.01" /></>),
  AlertCircle: makeIcon(<><circle cx="12" cy="12" r="9" /><path d="M12 8v4M12 16h.01" /></>),
  Loader:    makeIcon(<><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" /></>),
  Clock:     makeIcon(<><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>),
  Filter:    makeIcon(<><path d="M3 5h18l-7 9v6l-4-2v-4Z" /></>),
  RefreshCw: makeIcon(<><path d="M3 12a9 9 0 0 1 15-6.7L21 8" /><path d="M21 3v5h-5" /><path d="M21 12a9 9 0 0 1-15 6.7L3 16" /><path d="M3 21v-5h5" /></>),
  ExternalLink: makeIcon(<><path d="M15 3h6v6" /><path d="m10 14 11-11" /><path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5" /></>),
  Eye:       makeIcon(<><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>),
  ArrowLeft: makeIcon(<><path d="M19 12H5M12 19l-7-7 7-7" /></>),
  FileText:  makeIcon(<><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6M8 13h8M8 17h6" /></>),
  FilePlus:  makeIcon(<><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /><path d="M12 12v6M9 15h6" /></>),
  FileEdit:  makeIcon(<><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h6" /><path d="M14 2v6h6" /><path d="M18 13.5 21 16.5l-5 5h-3v-3z" /></>),
  Pause:     makeIcon(<><rect x="6" y="5" width="4" height="14" /><rect x="14" y="5" width="4" height="14" /></>),
  StopCircle: makeIcon(<><circle cx="12" cy="12" r="9" /><rect x="9" y="9" width="6" height="6" /></>),
  Layers:    makeIcon(<><path d="m12 2 10 5-10 5L2 7Z" /><path d="m2 12 10 5 10-5" /><path d="m2 17 10 5 10-5" /></>),
  Zap:       makeIcon(<><path d="M13 2 3 14h7v8l10-12h-7Z" /></>),
  Settings:  makeIcon(<><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.8l-.1-.1A2 2 0 1 1 7 4.3l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></>),
  Cpu:       makeIcon(<><rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" /><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3" /></>),
  Activity:  makeIcon(<><path d="M22 12h-4l-3 9-6-18-3 9H2" /></>),
  Compass:   makeIcon(<><circle cx="12" cy="12" r="9" /><path d="m16 8-2 6-6 2 2-6Z" /></>),
  ListTree:  makeIcon(<><path d="M3 5h6M3 12h6M3 19h6M13 5h8M13 12h8M13 19h8" /></>),
  GitBranch: makeIcon(<><circle cx="6" cy="3" r="2" /><circle cx="6" cy="18" r="2" /><circle cx="18" cy="6" r="2" /><path d="M6 5v8a4 4 0 0 0 4 4h2a4 4 0 0 0 4-4V8" /></>),
  ArrowUpRight: makeIcon(<><path d="M7 17 17 7M8 7h9v9" /></>),
  Hash:      makeIcon(<><path d="M4 9h16M4 15h16M10 3 8 21M16 3l-2 18" /></>),
  User:      makeIcon(<><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>),
  Sparkles:  makeIcon(<><path d="m12 3 2 5 5 2-5 2-2 5-2-5-5-2 5-2Z" /></>),
};

// ---- Button ----------------------------------------------------------------
function KbButton({ variant = "secondary", size = "md", className, children, ...rest }) {
  const variants = {
    primary: "bg-brand text-white hover:bg-brand-hover shadow-sm",
    secondary: "bg-bg-muted text-ink hover:bg-line-soft border border-line",
    ghost: "bg-transparent text-ink-soft hover:bg-bg-muted",
    outline: "bg-bg-surface text-ink border border-line hover:bg-bg-muted",
    danger: "bg-status-err text-white hover:bg-red-700 shadow-sm",
    dark: "bg-sidebar-active text-white hover:bg-sidebar-hover",
  };
  const sizes = {
    sm: "h-8 px-3 text-xs",
    md: "h-9 px-4 text-sm",
    lg: "h-11 px-5 text-base",
    icon: "h-9 w-9",
  };
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors",
        "disabled:opacity-50 disabled:pointer-events-none",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-brand/30",
        variants[variant], sizes[size], className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

// ---- Badge -----------------------------------------------------------------
function KbBadge({ tone = "neutral", className, children, dot = false }) {
  const tones = {
    ok:      "bg-status-okSoft text-status-ok",
    warn:    "bg-status-warnSoft text-status-warn",
    err:     "bg-status-errSoft text-status-err",
    info:    "bg-status-infoSoft text-status-info",
    neutral: "bg-status-neutralSoft text-status-neutral",
    brand:   "bg-brand-soft text-brand",
    dark:    "bg-sidebar-active text-sidebar-text",
  };
  const dotColors = {
    ok: "bg-status-ok", warn: "bg-status-warn", err: "bg-status-err",
    info: "bg-status-info", neutral: "bg-status-neutral", brand: "bg-brand", dark: "bg-sidebar-text",
  };
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
      tones[tone], className,
    )}>
      {dot && <span className={cn("h-1.5 w-1.5 rounded-full", dotColors[tone])} />}
      {children}
    </span>
  );
}

// ---- Status helpers --------------------------------------------------------
function statusMeta(status) {
  switch (status) {
    case "completed":  return { tone: "ok",   label: "Completed" };
    case "extracting": return { tone: "info", label: "Extracting" };
    case "scouting":   return { tone: "info", label: "Scouting" };
    case "qa":         return { tone: "info", label: "QA" };
    case "queued":     return { tone: "warn", label: "Queued" };
    case "failed":     return { tone: "err",  label: "Failed" };
    case "review":     return { tone: "warn", label: "Needs review" };
    default:           return { tone: "neutral", label: status };
  }
}

function StatusBadge({ status, className }) {
  const meta = statusMeta(status);
  const tone = meta.tone;
  const isRunning = status === "extracting" || status === "scouting" || status === "qa";
  return (
    <KbBadge tone={tone} className={className}>
      {isRunning ? (
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inset-0 animate-ping rounded-full bg-status-info opacity-75" />
          <span className="relative h-1.5 w-1.5 rounded-full bg-status-info" />
        </span>
      ) : status === "queued" ? (
        <I.Clock className="h-3 w-3" />
      ) : status === "completed" ? (
        <I.CheckCircle className="h-3 w-3" />
      ) : status === "failed" ? (
        <I.XCircle className="h-3 w-3" />
      ) : null}
      {meta.label}
    </KbBadge>
  );
}

// ---- Card ------------------------------------------------------------------
function KbCard({ className, children, ...rest }) {
  return (
    <div className={cn("rounded-xl border border-line bg-bg-surface shadow-card", className)} {...rest}>
      {children}
    </div>
  );
}

// ---- Phase pill (used in tree + detail header) -----------------------------
function PhaseDot({ phase }) {
  const i = window.kbPhaseIndex(phase);
  const colors = ["#94A3B8", "#2563EB", "#7C3AED", "#0EA5E9", "#16A34A"];
  if (phase === "failed") return <span className="h-2 w-2 rounded-full bg-status-err" />;
  return <span className="h-2 w-2 rounded-full" style={{ background: colors[i] }} />;
}

// ---- Progress bar ----------------------------------------------------------
function KbProgress({ value, status, className }) {
  const pct = Math.max(0, Math.min(100, value));
  const fill =
    status === "completed" ? "bg-status-ok" :
    status === "failed"    ? "bg-status-err" :
    status === "queued"    ? "bg-status-warn" :
    "bg-status-info";
  return (
    <div className={cn("h-1.5 overflow-hidden rounded-full bg-line-soft", className)}>
      <div className={cn("h-full rounded-full transition-all", fill)} style={{ width: pct + "%" }} />
    </div>
  );
}

Object.assign(window, {
  cn, I, KbButton, KbBadge, statusMeta, StatusBadge, KbCard, PhaseDot, KbProgress,
});
