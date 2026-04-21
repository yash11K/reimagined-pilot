import { useState, useEffect } from "react";
import { useWorkerStatus } from "@/hooks/useWorkerStatus";
import { Card, CardHeader, CardBody } from "@/components/ui/Card";
import type { WorkerState } from "@/types/api";

/** Small sub-component that ticks every second showing elapsed time from `startedAt`. */
function ElapsedTimer({ startedAt }: { startedAt: number }) {
  const [elapsed, setElapsed] = useState(() =>
    Math.floor((Date.now() - startedAt) / 1000)
  );

  useEffect(() => {
    setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, [startedAt]);

  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  const display = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;

  return <span className="text-xs tabular-nums text-ink-muted">{display}</span>;
}

function truncateUrl(url: string, max = 40): string {
  return url.length > max ? url.slice(0, max) + "…" : url;
}

function WorkerCard({ worker }: { worker: WorkerState }) {
  const isActive = worker.status === "active";

  return (
    <Card className="min-w-[200px] flex-1">
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            <span
              className={
                isActive
                  ? "inline-block h-2.5 w-2.5 rounded-full bg-green-500 animate-pulse"
                  : "inline-block h-2.5 w-2.5 rounded-full bg-gray-400"
              }
            />
            Worker {worker.workerId}
          </span>
        }
      />
      <CardBody className="space-y-1">
        {isActive ? (
          <>
            <p
              className="truncate text-xs text-ink-muted"
              title={worker.url ?? ""}
            >
              {truncateUrl(worker.url ?? "")}
            </p>
            <p className="text-xs font-medium text-ink">{worker.phase}</p>
            {worker.startedAt != null && (
              <ElapsedTimer startedAt={worker.startedAt} />
            )}
          </>
        ) : (
          <p className="text-xs text-ink-muted/60">Idle</p>
        )}
      </CardBody>
    </Card>
  );
}

export function WorkerCards() {
  const workers = useWorkerStatus();

  return (
    <div className="flex gap-4">
      {workers.map((w) => (
        <WorkerCard key={w.workerId} worker={w} />
      ))}
    </div>
  );
}
