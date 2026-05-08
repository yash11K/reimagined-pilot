import { ChevronRight, Globe, Loader2, Lock, RefreshCw } from "lucide-react";
import { useNavigate } from "react-router-dom";
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
import { fmtRelTime } from "@/lib/format";
import { isRunning, prettyUrl, type DisplayStatus } from "@/lib/kbStatus";
import type { SourceSummary } from "@/types/api";
import { ConnectorChip } from "./ConnectorChip";
import { MiniPhaseTrack } from "./MiniPhaseTrack";
import { SourceStatusBadge } from "./SourceStatusBadge";

export interface SourceRow extends SourceSummary {
  displayStatus: DisplayStatus;
}

interface Props {
  sources: SourceRow[];
  onReingest?: (s: SourceRow) => void;
  reingestPending?: string | null;
}

export function SourcesTable({ sources, onReingest, reingestPending }: Props) {
  const nav = useNavigate();
  const open = (s: SourceRow) => nav(`/knowledge-base/${s.id}`);

  return (
    <DataTable>
      <Table>
        <Thead>
          <tr>
            <Th>Source</Th>
            <Th>Status</Th>
            <Th>Pipeline</Th>
            <Th className="text-right">Runs</Th>
            <Th>Last run</Th>
            <Th>Added</Th>
            <Th className="text-right">Actions</Th>
          </tr>
        </Thead>
        <Tbody>
          {sources.length === 0 ? (
            <EmptyRow colSpan={7} message="No sources match your filters." />
          ) : (
            sources.map((src) => {
              const running = isRunning(src.displayStatus);
              const blocked = !!src.active_job_id;
              const canReingest =
                !blocked &&
                (src.displayStatus === "idle" || src.displayStatus === "failed");
              return (
                <Tr key={src.id} className="cursor-pointer" onClick={() => open(src)}>
                  <Td>
                    <div className="flex items-center gap-2.5">
                      <ConnectorChip type={src.type} />
                      {src.kb_target === "internal" ? (
                        <Lock className="h-3 w-3 text-ink-faint" />
                      ) : (
                        <Globe className="h-3 w-3 text-ink-faint" />
                      )}
                    </div>
                    <div className="mt-1 max-w-[420px] truncate text-sm font-medium text-ink">
                      {prettyUrl(src.url)}
                    </div>
                  </Td>
                  <Td>
                    <SourceStatusBadge status={src.displayStatus} />
                  </Td>
                  <Td>
                    <MiniPhaseTrack status={src.displayStatus} />
                  </Td>
                  <Td className="text-right text-xs tabular-nums text-ink-muted">
                    {src.run_count}
                  </Td>
                  <Td className="text-xs text-ink-muted">
                    {fmtRelTime(src.last_run_at)}
                  </Td>
                  <Td className="text-xs text-ink-muted">
                    {fmtRelTime(src.created_at)}
                  </Td>
                  <Td className="text-right" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center justify-end gap-1">
                      {running ? (
                        <span className="inline-flex items-center gap-1 px-2 text-[11px] text-ink-muted">
                          <Loader2 className="h-3 w-3 animate-spin" /> running
                        </span>
                      ) : (
                        canReingest &&
                        onReingest && (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={reingestPending === src.id}
                            onClick={() => onReingest(src)}
                          >
                            <RefreshCw className="h-3 w-3" /> Re-ingest
                          </Button>
                        )
                      )}
                      <button
                        onClick={() => open(src)}
                        className="rounded-md p-1.5 text-ink-muted hover:bg-bg-muted hover:text-ink"
                      >
                        <ChevronRight className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </Td>
                </Tr>
              );
            })
          )}
        </Tbody>
      </Table>
    </DataTable>
  );
}
