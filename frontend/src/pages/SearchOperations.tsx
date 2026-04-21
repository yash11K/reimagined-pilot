import { useState } from "react";
import {
  Search as SearchIcon,
  TrendingUp,
  Clock,
  AlertTriangle,
  ArrowUp,
  ArrowDown,
} from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { KpiCard } from "@/components/ui/KpiCard";
import { DataTable, Table, Thead, Th, Tbody, Tr, Td } from "@/components/ui/Table";
import { Badge, statusTone } from "@/components/ui/Badge";
import { cn } from "@/lib/cn";

// ALL MOCK — backend has stub /kb/search only. Flag DEMO clearly.

const RANGES = ["24h", "7d", "30d", "90d"] as const;
type Range = (typeof RANGES)[number];

const QUERIES = [
  { q: "cancellation policy", vol: 1523, success: 96, trend: "up", resp: 0.3, status: "HEALTHY" },
  { q: "damage waiver", vol: 1247, success: 92, trend: "up", resp: 0.4, status: "HEALTHY" },
  { q: "pet policy", vol: 892, success: 78, trend: "down", resp: 0.6, status: "CRITICAL" },
  { q: "insurance coverage", vol: 2103, success: 94, trend: "up", resp: 0.3, status: "HEALTHY" },
  { q: "loyalty rewards", vol: 1634, success: 91, trend: "flat", resp: 0.4, status: "HEALTHY" },
  { q: "branch hours", vol: 3421, success: 98, trend: "up", resp: 0.2, status: "HEALTHY" },
];

export default function SearchOperations() {
  const [range, setRange] = useState<Range>("7d");

  return (
    <>
      <PageHeader
        title="Search Operations"
        subtitle="Monitor query performance, success rates, and response time across the KB."
        actions={
          <div className="flex items-center gap-1 rounded-lg border border-line bg-bg-muted p-1">
            {RANGES.map((r) => (
              <button
                key={r}
                onClick={() => setRange(r)}
                className={cn(
                  "rounded-md px-3 py-1 text-xs font-semibold transition-colors",
                  range === r
                    ? "bg-bg-surface text-ink shadow-sm"
                    : "text-ink-muted hover:text-ink"
                )}
              >
                {r}
              </button>
            ))}
          </div>
        }
      />

      <div className="mb-3 inline-flex items-center gap-2 rounded-lg border border-status-warn/30 bg-status-warnSoft px-3 py-1.5 text-xs font-medium text-status-warn">
        <AlertTriangle className="h-3.5 w-3.5" />
        All metrics on this page are demo data — backend <code className="rounded bg-bg-surface px-1">/kb/search</code> is stub.
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Total Searches"
          value="12,847"
          trend={{ value: "+12.4% vs last period", direction: "up" }}
          icon={SearchIcon}
          fake
        />
        <KpiCard
          label="Avg Success Rate"
          value="91.6%"
          trend={{ value: "+2.1pp", direction: "up" }}
          icon={TrendingUp}
          fake
        />
        <KpiCard
          label="Avg Response Time"
          value="0.35s"
          trend={{ value: "-0.05s", direction: "up" }}
          icon={Clock}
          fake
        />
        <KpiCard
          label="Failed Queries"
          value="1,079"
          trend={{ value: "-8.2%", direction: "up" }}
          icon={AlertTriangle}
          fake
        />
      </div>

      <div className="mt-6">
        <DataTable>
          <div className="flex items-center justify-between border-b border-line px-5 py-4">
            <div>
              <h3 className="text-sm font-semibold text-ink">Top Search Queries</h3>
              <p className="text-xs text-ink-muted">Ranked by volume for the selected window</p>
            </div>
            <Badge tone="warn">Demo</Badge>
          </div>
          <Table>
            <Thead>
              <tr>
                <Th>Query</Th>
                <Th>Volume</Th>
                <Th>Success %</Th>
                <Th>Trend</Th>
                <Th>Avg Response</Th>
                <Th>Status</Th>
              </tr>
            </Thead>
            <Tbody>
              {QUERIES.map((row) => (
                <Tr key={row.q}>
                  <Td className="font-medium text-ink">{row.q}</Td>
                  <Td className="tabular-nums">{row.vol.toLocaleString()}</Td>
                  <Td className="tabular-nums">{row.success}%</Td>
                  <Td>
                    {row.trend === "up" && <ArrowUp className="h-4 w-4 text-status-ok" />}
                    {row.trend === "down" && <ArrowDown className="h-4 w-4 text-status-err" />}
                    {row.trend === "flat" && <span className="text-ink-muted">—</span>}
                  </Td>
                  <Td className="tabular-nums">{row.resp}s</Td>
                  <Td>
                    <Badge tone={statusTone(row.status)}>{row.status}</Badge>
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </DataTable>
      </div>
    </>
  );
}
