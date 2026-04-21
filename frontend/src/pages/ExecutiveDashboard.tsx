import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  FileText,
  Link2,
  Clock,
  Search as SearchIcon,
  Activity,
  CheckCircle2,
  XCircle,
  PlayCircle,
  ChevronDown,
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
} from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { KpiCard } from "@/components/ui/KpiCard";
import { Card, CardHeader, CardBody } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import {
  SkeletonKpi,
  SkeletonBarChart,
  SkeletonActivity,
  SkeletonStatCard,
} from "@/components/ui/Skeleton";
import { Shimmer } from "@/components/ui/Shimmer";
import { getStats, getActivity } from "@/api/endpoints";
import { fmtNum, fmtRelTime } from "@/lib/format";
import { useBrand } from "@/contexts/BrandContext";
import { cn } from "@/lib/cn";

// ---------------------------------------------------------------------------
// Enriched Test-Case Performance Mock
// ---------------------------------------------------------------------------
type Trend = "up" | "down" | "flat";
type Severity = "pass" | "warn" | "fail";

interface TestCase {
  name: string;
  category: string;
  score: number;
  prevScore: number;
  trend: Trend;
  severity: Severity;
  runs: number;
  p95Latency: number;        // ms
  lastRun: string;           // ISO
  failureRate: number;       // 0-100
  topFailureReason: string | null;
  tags: string[];
}

function scoreSeverity(s: number): Severity {
  if (s >= 90) return "pass";
  if (s >= 75) return "warn";
  return "fail";
}

function scoreTrend(cur: number, prev: number): Trend {
  const d = cur - prev;
  if (d > 1) return "up";
  if (d < -1) return "down";
  return "flat";
}

const RAW_CASES: Omit<TestCase, "trend" | "severity">[] = [
  {
    name: "Cancellation policy retrieval",
    category: "Policy",
    score: 96,
    prevScore: 93,
    runs: 1_248,
    p95Latency: 320,
    lastRun: "2026-04-21T08:12:00Z",
    failureRate: 1.2,
    topFailureReason: null,
    tags: ["critical-path", "customer-facing"],
  },
  {
    name: "Damage waiver Q&A",
    category: "Policy",
    score: 88,
    prevScore: 91,
    runs: 874,
    p95Latency: 480,
    lastRun: "2026-04-21T07:55:00Z",
    failureRate: 4.8,
    topFailureReason: "Partial answer — missing CDW tier details",
    tags: ["customer-facing"],
  },
  {
    name: "Branch hours lookup",
    category: "Operations",
    score: 84,
    prevScore: 82,
    runs: 2_310,
    p95Latency: 210,
    lastRun: "2026-04-21T08:20:00Z",
    failureRate: 6.1,
    topFailureReason: "Holiday schedule not indexed",
    tags: ["high-volume"],
  },
  {
    name: "Loyalty program benefits",
    category: "Marketing",
    score: 79,
    prevScore: 80,
    runs: 562,
    p95Latency: 540,
    lastRun: "2026-04-20T23:30:00Z",
    failureRate: 9.3,
    topFailureReason: "Outdated tier thresholds returned",
    tags: ["needs-attention"],
  },
  {
    name: "Roadside assistance flow",
    category: "Operations",
    score: 92,
    prevScore: 89,
    runs: 1_045,
    p95Latency: 290,
    lastRun: "2026-04-21T06:40:00Z",
    failureRate: 2.0,
    topFailureReason: null,
    tags: ["critical-path"],
  },
  {
    name: "Insurance upsell eligibility",
    category: "Sales",
    score: 71,
    prevScore: 68,
    runs: 430,
    p95Latency: 620,
    lastRun: "2026-04-21T05:10:00Z",
    failureRate: 12.4,
    topFailureReason: "State-specific rules missing for 3 states",
    tags: ["needs-attention", "revenue-impact"],
  },
  {
    name: "Vehicle class comparison",
    category: "Sales",
    score: 86,
    prevScore: 87,
    runs: 1_780,
    p95Latency: 350,
    lastRun: "2026-04-21T08:05:00Z",
    failureRate: 3.5,
    topFailureReason: null,
    tags: ["high-volume", "customer-facing"],
  },
  {
    name: "Corporate rate lookup",
    category: "Sales",
    score: 94,
    prevScore: 92,
    runs: 920,
    p95Latency: 270,
    lastRun: "2026-04-21T07:30:00Z",
    failureRate: 1.8,
    topFailureReason: null,
    tags: ["critical-path"],
  },
];

const TEST_CASES: TestCase[] = RAW_CASES.map((c) => ({
  ...c,
  trend: scoreTrend(c.score, c.prevScore),
  severity: scoreSeverity(c.score),
}));

const CATEGORIES = ["All", ...Array.from(new Set(RAW_CASES.map((c) => c.category)))];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const trendIcon = (t: Trend) => {
  if (t === "up") return <TrendingUp className="h-3 w-3 text-status-ok" />;
  if (t === "down") return <TrendingDown className="h-3 w-3 text-status-err" />;
  return <Minus className="h-3 w-3 text-ink-faint" />;
};

const severityBar: Record<Severity, string> = {
  pass: "bg-status-ok",
  warn: "bg-status-warn",
  fail: "bg-status-err",
};

const activityIcon = (type: string) => {
  if (type.includes("approved")) return <CheckCircle2 className="h-4 w-4 text-status-ok" />;
  if (type.includes("rejected")) return <XCircle className="h-4 w-4 text-status-err" />;
  if (type.includes("failed")) return <XCircle className="h-4 w-4 text-status-err" />;
  if (type.includes("completed")) return <CheckCircle2 className="h-4 w-4 text-status-ok" />;
  return <PlayCircle className="h-4 w-4 text-status-info" />;
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function ExecutiveDashboard() {
  const { brand } = useBrand();
  const [catFilter, setCatFilter] = useState("All");
  const [expanded, setExpanded] = useState<string | null>(null);

  const statsQ = useQuery({
    queryKey: ["stats", brand],
    queryFn: getStats,
  });
  const activityQ = useQuery({
    queryKey: ["activity", brand],
    queryFn: () => getActivity(15),
  });

  const stats = statsQ.data;

  const filteredCases = useMemo(
    () =>
      catFilter === "All"
        ? TEST_CASES
        : TEST_CASES.filter((c) => c.category === catFilter),
    [catFilter],
  );

  const avgScore = useMemo(
    () => Math.round(filteredCases.reduce((s, c) => s + c.score, 0) / (filteredCases.length || 1)),
    [filteredCases],
  );

  return (
    <>
      <PageHeader
        title="ABG Command Center"
        subtitle="Knowledge Operations Dashboard. Plan with confidence. Operate with clarity."
      />

      {/* ── KPI Row ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Shimmer
          loading={statsQ.isLoading}
          fallback={
            <>
              <SkeletonKpi />
              <SkeletonKpi />
              <SkeletonKpi />
              <SkeletonKpi />
            </>
          }
          className="contents"
        >
          <KpiCard
            label="Published Articles"
            value={fmtNum(stats?.approved)}
            trend={{ value: "+4.2% QoQ", direction: "up" }}
            icon={FileText}
          />
          <KpiCard
            label="Connected Sources"
            value={fmtNum(stats?.sources_count)}
            hint={`${stats?.active_jobs ?? 0} active jobs`}
            icon={Link2}
          />
          <KpiCard
            label="Approvals Due"
            value={fmtNum(stats?.pending_review)}
            hint="pending review"
            icon={Clock}
          />
          <KpiCard
            label="Search Success"
            value="91.6%"
            trend={{ value: "+2.1pp", direction: "up" }}
            icon={SearchIcon}
            fake
          />
        </Shimmer>
      </div>

      {/* ── Test Case Performance + Recent Activity ──────────── */}
      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Test Case Performance */}
        <Card className="lg:col-span-2">
          <CardHeader
            title="Test Case Performance"
            subtitle="Aggregated retrieval quality across critical knowledge journeys"
            action={
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold tabular-nums text-ink">
                  Avg {avgScore}%
                </span>
                <span className="rounded bg-status-warnSoft px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-status-warn">
                  Demo Data
                </span>
              </div>
            }
          />

          {/* Category filter pills */}
          <div className="flex flex-wrap gap-1.5 px-5 pb-2">
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                onClick={() => setCatFilter(cat)}
                className={cn(
                  "rounded-full px-2.5 py-0.5 text-[11px] font-medium transition-colors",
                  catFilter === cat
                    ? "bg-brand text-white"
                    : "bg-bg-muted text-ink-muted hover:bg-bg-surface hover:text-ink",
                )}
              >
                {cat}
              </button>
            ))}
          </div>

          <CardBody className="space-y-2">
            {filteredCases.map((t) => {
              const isOpen = expanded === t.name;
              return (
                <div key={t.name} className="rounded-lg border border-line-soft">
                  {/* Summary row */}
                  <button
                    onClick={() => setExpanded(isOpen ? null : t.name)}
                    className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-bg-muted/50"
                  >
                    <ChevronDown
                      className={cn(
                        "h-3.5 w-3.5 shrink-0 text-ink-faint transition-transform",
                        isOpen && "rotate-180",
                      )}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-xs font-medium text-ink">{t.name}</span>
                        <span className="shrink-0 rounded bg-bg-muted px-1.5 py-0.5 text-[10px] text-ink-muted">
                          {t.category}
                        </span>
                      </div>
                      <div className="mt-1 h-1.5 w-full rounded-full bg-bg-muted">
                        <div
                          className={cn("h-1.5 rounded-full transition-all", severityBar[t.severity])}
                          style={{ width: `${t.score}%` }}
                        />
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      {trendIcon(t.trend)}
                      <span className="w-9 text-right text-xs font-semibold tabular-nums text-ink">
                        {t.score}%
                      </span>
                    </div>
                  </button>

                  {/* Expanded detail */}
                  {isOpen && (
                    <div className="border-t border-line-soft bg-bg-muted/30 px-4 py-3">
                      <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-4">
                        <div>
                          <span className="text-ink-faint">Prev Score</span>
                          <p className="font-medium tabular-nums text-ink">{t.prevScore}%</p>
                        </div>
                        <div>
                          <span className="text-ink-faint">Total Runs</span>
                          <p className="font-medium tabular-nums text-ink">{fmtNum(t.runs)}</p>
                        </div>
                        <div>
                          <span className="text-ink-faint">P95 Latency</span>
                          <p className="font-medium tabular-nums text-ink">{t.p95Latency}ms</p>
                        </div>
                        <div>
                          <span className="text-ink-faint">Failure Rate</span>
                          <p className={cn(
                            "font-medium tabular-nums",
                            t.failureRate > 5 ? "text-status-err" : "text-ink",
                          )}>
                            {t.failureRate}%
                          </p>
                        </div>
                      </div>
                      {t.topFailureReason && (
                        <div className="mt-2 flex items-start gap-1.5 rounded bg-status-errSoft/40 px-2 py-1.5 text-xs text-status-err">
                          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                          <span>{t.topFailureReason}</span>
                        </div>
                      )}
                      {t.tags.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {t.tags.map((tag) => (
                            <span
                              key={tag}
                              className="rounded-full bg-bg-muted px-2 py-0.5 text-[10px] font-medium text-ink-muted"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                      <p className="mt-1.5 text-[10px] text-ink-faint">
                        Last run {fmtRelTime(t.lastRun)}
                      </p>
                    </div>
                  )}
                </div>
              );
            })}
          </CardBody>
        </Card>

        {/* Recent Activity — scrollable */}
        <Card className="flex flex-col">
          <CardHeader
            title="Recent Activity"
            subtitle="Latest actions across the workspace"
            action={<Activity className="h-4 w-4 text-ink-faint" />}
          />
          <CardBody className="min-h-0 flex-1 overflow-y-auto pr-2" style={{ maxHeight: "26rem" }}>
            {activityQ.isLoading && <SkeletonActivity rows={6} />}
            {activityQ.isError && (
              <p className="text-xs text-status-err">
                Activity feed unavailable. Backend may not have the endpoint yet.
              </p>
            )}
            {!activityQ.isLoading && activityQ.data?.items?.length === 0 && (
              <p className="text-xs text-ink-muted">No recent activity.</p>
            )}
            <div className="space-y-3">
              {activityQ.data?.items?.map((a) => (
                <div key={a.id} className="flex items-start gap-3 border-b border-line-soft pb-3 last:border-0">
                  <div className="mt-0.5">{activityIcon(a.type)}</div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-ink">
                      {a.actor ?? "System"}{" "}
                      <span className="text-ink-muted">{a.action}</span>
                    </p>
                    <p className="truncate text-xs text-ink-muted">{a.target_title}</p>
                  </div>
                  <span className="shrink-0 text-[10px] text-ink-faint">
                    {fmtRelTime(a.timestamp)}
                  </span>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      </div>

      {/* ── Stat cards row ──────────────────────────────────────── */}
      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Shimmer
          loading={statsQ.isLoading}
          fallback={
            <>
              <SkeletonStatCard />
              <SkeletonStatCard />
              <SkeletonStatCard />
            </>
          }
          className="contents"
        >
          <Card>
            <CardHeader title="Source Reliability" />
            <CardBody>
              <div className="flex items-baseline justify-between text-sm">
                <span className="text-ink-muted">Trusted</span>
                <span className="text-2xl font-semibold tabular-nums text-status-ok">
                  {fmtNum(stats?.sources_count)}
                </span>
              </div>
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Approved Files" />
            <CardBody>
              <div className="flex items-baseline justify-between text-sm">
                <span className="text-ink-muted">Total</span>
                <span className="text-2xl font-semibold tabular-nums text-ink">
                  {fmtNum(stats?.approved)}
                </span>
              </div>
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Rejected" />
            <CardBody>
              <div className="flex items-baseline justify-between text-sm">
                <span className="text-ink-muted">Total</span>
                <span className="text-2xl font-semibold tabular-nums text-status-err">
                  {fmtNum(stats?.rejected)}
                </span>
              </div>
            </CardBody>
          </Card>
        </Shimmer>
      </div>

      {/* ── Search Quality by Audience ──────────────────────────── */}
      <div className="mt-6">
        <Card>
          <CardHeader
            title="Search Quality by Audience"
            action={<Badge tone="warn">Demo</Badge>}
          />
          <CardBody className="space-y-3">
            {[
              { name: "Customer care", score: 94 },
              { name: "Branch agents", score: 90 },
              { name: "Claims ops", score: 87 },
            ].map((s) => (
              <div key={s.name}>
                <div className="mb-1 flex items-center justify-between text-xs">
                  <span className="font-medium text-ink-soft">{s.name}</span>
                  <span className="font-semibold tabular-nums text-ink">{s.score}%</span>
                </div>
                <div className="h-2 w-full rounded-full bg-bg-muted">
                  <div className="h-2 rounded-full bg-status-info" style={{ width: `${s.score}%` }} />
                </div>
              </div>
            ))}
          </CardBody>
        </Card>
      </div>
    </>
  );
}
