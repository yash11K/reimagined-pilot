import { PageHeader } from "@/components/ui/PageHeader";
import { LivePipelineStrip } from "@/components/discovery/LivePipelineStrip";
import { WorkerCards } from "@/components/discovery/WorkerCards";
import { QueueSubmitForm } from "@/components/discovery/QueueSubmitForm";
import { QueueTable } from "@/components/discovery/QueueTable";

export default function Operations() {
  return (
    <>
      <PageHeader
        title="Operations"
        subtitle="Worker health, queue management, and live pipeline telemetry."
      />

      <div className="space-y-6">
        <WorkerCards />

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2 space-y-4">
            <QueueSubmitForm />
            <QueueTable />
          </div>
          <LivePipelineStrip />
        </div>
      </div>
    </>
  );
}
