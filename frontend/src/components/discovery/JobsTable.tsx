import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Eye, CheckCircle2, Loader2, XCircle, AlertCircle, Database } from "lucide-react";
import { Card, CardHeader, CardBody } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import {
  DataTable,
  Table,
  Thead,
  Th,
  Tbody,
  Tr,
  Td,
  EmptyRow,
} from "@/components/ui/Table";
import { fmtNum, fmtRelTime } from "@/lib/format";
import { listJobs } from "@/api/endpoints";
import { useBrand } from "@/contexts/BrandContext";
import type { JobSummary, JobStatus } from "@/types/api";
import { JobDetailsDrawer } from "./JobDetailsDrawer";

function statusBadge(status: JobStatus) {
  switch (status) {
    case "completed":
      return (
        <Badge tone="ok">
          <CheckCircle2 className="h-3 w-3" /> Completed
        </Badge>
      );
    case "processing":
    case "scouting":
      return (
        <Badge tone="info">
          <Loader2 className="h-3 w-3 animate-spin" /> Running
        </Badge>
      );
    case "failed":
      return (
        <Badge tone="err">
          <XCircle className="h-3 w-3" /> Failed
        </Badge>
      );
    case "awaiting_confirmation":
      return (
        <Badge tone="warn">
          <AlertCircle className="h-3 w-3" /> Needs Review
        </Badge>
      );
  }
}

function progressBarColor(status: JobStatus): string {
  switch (status) {
    case "completed":
      return "bg-status-ok";
    case "failed":
      return "bg-status-err";
    case "awaiting_confirmation":
      return "bg-status-warn";
    default:
      return "bg-status-info";
  }
}

function ProgressCell({ job }: { job: JobSummary }) {
  const pct = Math.max(0, Math.min(100, job.progress_pct));
  return (
    <div className="flex items-center gap-2 min-w-[140px]">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-line-soft">
        <div
          className={`h-full rounded-full transition-all ${progressBarColor(job.status)}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-ink-muted tabular-nums w-9 text-right">{pct}%</span>
    </div>
  );
}

export function JobsTable() {
  const { brandParam } = useBrand();
  const [selected, setSelected] = useState<JobSummary | null>(null);

  const jobs = useQuery({
    queryKey: ["jobs", brandParam()],
    queryFn: () =>
      listJobs({
        page: 1,
        size: 25,
        brand: brandParam(),
        sort: "started_at:desc",
      }),
  });

  const rows = useMemo(() => jobs.data?.items ?? [], [jobs.data]);
  const isLoading = jobs.isLoading;

  return (
    <>
      <Card>
        <CardHeader
          title="Discovery Jobs"
          subtitle="Manage automated content discovery and ingestion pipelines"
        />
        <CardBody className="max-h-[520px] overflow-y-auto p-0">
          <DataTable className="border-0 shadow-none rounded-none">
            <Table>
              <Thead>
                <tr className="sticky top-0 z-10">
                  <Th>Job Name</Th>
                  <Th>Source</Th>
                  <Th>Status</Th>
                  <Th>Progress</Th>
                  <Th className="text-right">Discovered</Th>
                  <Th>Last Run</Th>
                  <Th className="text-right">Actions</Th>
                </tr>
              </Thead>
              <Tbody>
                {isLoading ? (
                  <EmptyRow colSpan={7} message="Loading jobs…" />
                ) : rows.length === 0 ? (
                  <EmptyRow
                    colSpan={7}
                    message="No discovery jobs yet. Click New Discovery Job to start."
                  />
                ) : (
                  rows.map((job) => (
                    <Tr key={job.id}>
                      <Td className="font-medium text-ink">{job.source_label}</Td>
                      <Td>
                        <div className="inline-flex items-center gap-1.5 text-ink-soft">
                          <Database className="h-3.5 w-3.5 text-ink-muted" />
                          <span className="text-xs">{job.source_type}</span>
                        </div>
                      </Td>
                      <Td>{statusBadge(job.status)}</Td>
                      <Td>
                        <ProgressCell job={job} />
                      </Td>
                      <Td className="text-right tabular-nums">
                        {job.status === "failed" || job.status === "scouting"
                          ? "—"
                          : fmtNum(job.discovered_count)}
                      </Td>
                      <Td className="text-xs">
                        {job.status === "processing" || job.status === "scouting"
                          ? "In progress"
                          : fmtRelTime(job.completed_at ?? job.started_at)}
                      </Td>
                      <Td className="text-right">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setSelected(job)}
                        >
                          <Eye className="h-3.5 w-3.5" /> View Details
                        </Button>
                      </Td>
                    </Tr>
                  ))
                )}
              </Tbody>
            </Table>
          </DataTable>
        </CardBody>
      </Card>

      <JobDetailsDrawer
        job={selected}
        open={selected != null}
        onClose={() => setSelected(null)}
      />
    </>
  );
}
