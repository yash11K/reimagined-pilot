import type { JobStatus, SourceSummary } from "@/types/api";

export type KbConnectorId = "aem" | "helpcms" | "magnolia" | "confluence";

export interface KbConnector {
  id: KbConnectorId;
  label: string;
  fullName: string;
  enabled: boolean;
  color: string;
  description: string;
}

export const KB_CONNECTORS: KbConnector[] = [
  {
    id: "aem",
    label: "AEM",
    fullName: "Adobe Experience Manager",
    enabled: true,
    color: "#2563EB",
    description: "Public website + internal authoring pages",
  },
  {
    id: "helpcms",
    label: "HelpCMS",
    fullName: "Help Center CMS",
    enabled: false,
    color: "#9333EA",
    description: "Salesforce-backed customer help articles",
  },
  {
    id: "magnolia",
    label: "Magnolia",
    fullName: "Magnolia DX Platform",
    enabled: false,
    color: "#0EA5E9",
    description: "Loyalty + corporate microsites",
  },
  {
    id: "confluence",
    label: "Confluence",
    fullName: "Atlassian Confluence",
    enabled: false,
    color: "#0891B2",
    description: "Internal team knowledge wikis",
  },
];

export function lookupConnector(type: string | null | undefined): KbConnector | null {
  if (!type) return null;
  return KB_CONNECTORS.find((c) => c.id === type) ?? null;
}

export type DisplayStatus =
  | "idle"
  | "queued"
  | "discovering"
  | "extracting"
  | "qa"
  | "failed"
  | "needs_review";

export const KB_PHASES = [
  { id: "queued", label: "Queued" },
  { id: "discovering", label: "Discovery" },
  { id: "extracting", label: "Extracting" },
  { id: "qa", label: "QA" },
  { id: "done", label: "Done" },
] as const;

export type KbPhaseId = (typeof KB_PHASES)[number]["id"];

export function statusToPhase(status: DisplayStatus): KbPhaseId {
  if (status === "queued") return "queued";
  if (status === "discovering") return "discovering";
  if (status === "extracting") return "extracting";
  if (status === "qa") return "qa";
  return "done";
}

export function phaseIndex(phase: KbPhaseId): number {
  const i = KB_PHASES.findIndex((p) => p.id === phase);
  return i < 0 ? 0 : i;
}

/**
 * Backend now returns `display_status` directly. Kept as a fallback merge for
 * stale payloads (e.g. websocket pushes without display_status).
 */
export function deriveDisplayStatus(
  source: SourceSummary,
  activeJobStatus?: JobStatus,
): DisplayStatus {
  if (source.status === "needs_confirmation") return "needs_review";
  if (source.status === "failed") return "failed";

  if (activeJobStatus === "scouting") return "discovering";
  if (activeJobStatus === "processing") return "extracting";
  if (activeJobStatus === "awaiting_confirmation") return "needs_review";
  if (activeJobStatus === "failed") return "failed";

  if (source.status === "ingested") return "idle";
  if (source.status === "active") return "queued";
  return "idle";
}

export function statusLabel(s: DisplayStatus): string {
  switch (s) {
    case "idle":
      return "Idle";
    case "queued":
      return "Queued";
    case "discovering":
      return "Discovering";
    case "extracting":
      return "Extracting";
    case "qa":
      return "QA";
    case "failed":
      return "Failed";
    case "needs_review":
      return "Needs review";
  }
}

export const RUNNING_STATUSES: DisplayStatus[] = ["discovering", "extracting", "qa"];
export function isRunning(s: DisplayStatus): boolean {
  return RUNNING_STATUSES.includes(s);
}

export function prettyUrl(url: string): string {
  try {
    const u = new URL(url);
    const out = (u.hostname.replace(/^www\./, "") + u.pathname).replace(/\/$/, "");
    return out || u.hostname;
  } catch {
    return url;
  }
}
