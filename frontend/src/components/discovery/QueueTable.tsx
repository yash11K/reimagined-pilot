import { useState, useRef, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getQueueItems } from "@/api/endpoints";
import { useSSEv2 } from "@/hooks/useSSEv2";
import { Badge } from "@/components/ui/Badge";
import { DataTable, Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from "@/components/ui/Table";
import { Pagination } from "@/components/ui/Pagination";
import { fmtRelTime } from "@/lib/format";
import type { QueueItem } from "@/types/api";

/* ------------------------------------------------------------------ */
/*  Display-status derivation                                         */
/* ------------------------------------------------------------------ */

type BadgeTone = "ok" | "warn" | "err" | "info" | "neutral";

interface DisplayStatus {
  label: string;
  tone: BadgeTone;
}

export function getDisplayStatus(item: QueueItem): DisplayStatus {
  if (item.status === "failed") {
    if (item.retry_count >= item.max_retries) {
      return { label: "exhausted", tone: "err" };
    }
    return { label: "requeued", tone: "warn" };
  }
  if (item.status === "processing") return { label: "processing", tone: "info" };
  if (item.status === "completed") return { label: "completed", tone: "ok" };
  return { label: "queued", tone: "neutral" };
}

/* ------------------------------------------------------------------ */
/*  SSE-triggered invalidation throttle (2 s)                         */
/* ------------------------------------------------------------------ */

const THROTTLE_MS = 2_000;

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */

const PAGE_SIZE = 20;

export function QueueTable() {
  const [page, setPage] = useState(1);
  const queryClient = useQueryClient();
  const lastInvalidateRef = useRef(0);

  /* ---- data fetch with 15 s polling ---- */
  const { data, isLoading } = useQuery({
    queryKey: ["queue", page],
    queryFn: () => getQueueItems({ page, size: PAGE_SIZE }),
    refetchInterval: 15_000,
  });

  /* ---- SSE subscription → throttled invalidation ---- */
  const { events } = useSSEv2({ topics: ["queue"] });

  useEffect(() => {
    if (events.length === 0) return;
    const now = Date.now();
    if (now - lastInvalidateRef.current > THROTTLE_MS) {
      lastInvalidateRef.current = now;
      queryClient.invalidateQueries({ queryKey: ["queue"] });
    }
  }, [events, queryClient]);

  /* ---- render ---- */
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <DataTable>
      <Table>
        <Thead>
          <Tr>
            <Th>URL</Th>
            <Th>Status</Th>
            <Th>Retries</Th>
            <Th>Priority</Th>
            <Th>Error</Th>
            <Th>Last Updated</Th>
          </Tr>
        </Thead>
        <Tbody>
          {isLoading && items.length === 0 ? (
            <EmptyRow colSpan={6} message="Loading queue items…" />
          ) : items.length === 0 ? (
            <EmptyRow colSpan={6} message="Queue is empty" />
          ) : (
            items.map((item) => {
              const ds = getDisplayStatus(item);
              return (
                <Tr key={item.id}>
                  <Td className="max-w-[280px] truncate" title={item.url}>
                    {item.url}
                  </Td>
                  <Td>
                    <Badge tone={ds.tone}>{ds.label}</Badge>
                  </Td>
                  <Td>
                    {item.retry_count > 0 ? (
                      <Badge tone="warn">
                        retry {item.retry_count}/{item.max_retries}
                      </Badge>
                    ) : (
                      "—"
                    )}
                  </Td>
                  <Td>
                    {item.priority > 0 ? (
                      <Badge tone="brand">{item.priority}</Badge>
                    ) : (
                      "—"
                    )}
                  </Td>
                  <Td className="max-w-[200px] truncate" title={item.error_message ?? undefined}>
                    {item.error_message ?? "—"}
                  </Td>
                  <Td>{fmtRelTime(item.updated_at)}</Td>
                </Tr>
              );
            })
          )}
        </Tbody>
      </Table>

      {total > PAGE_SIZE && (
        <Pagination page={page} size={PAGE_SIZE} total={total} onPage={setPage} />
      )}
    </DataTable>
  );
}
