import { useQuery } from "@tanstack/react-query";
import { FileText, ExternalLink, Sparkles } from "lucide-react";
import { Card, CardHeader, CardBody } from "@/components/ui/Card";
import { listSources } from "@/api/endpoints";
import { useBrand } from "@/contexts/BrandContext";
import { fmtRelTime } from "@/lib/format";

export function RecentDiscoveries() {
  const { brandParam } = useBrand();

  const { data, isLoading } = useQuery({
    queryKey: ["sources", "recent", brandParam()],
    queryFn: () =>
      listSources({
        page: 1,
        size: 10,
        parent_only: false,
        brand: brandParam(),
      }),
  });

  const items = (data?.items ?? [])
    .slice()
    .sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));

  return (
    <Card>
      <CardHeader
        title="Recent Discoveries"
        subtitle="Newly ingested or scouted sources"
        action={<Sparkles className="h-4 w-4 text-brand" />}
      />
      <CardBody>
        {isLoading && <p className="text-xs text-ink-muted">Loading…</p>}
        {!isLoading && items.length === 0 && (
          <p className="text-xs text-ink-muted">Nothing discovered in last 24h.</p>
        )}
        <ul className="space-y-2">
          {items.map((s) => (
            <li
              key={s.id}
              className="flex items-start gap-3 rounded-lg border border-line-soft bg-bg-muted p-3"
            >
              <FileText className="mt-0.5 h-4 w-4 shrink-0 text-ink-muted" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-ink" title={s.url}>
                  {s.url}
                </p>
                <p className="mt-0.5 text-xs text-ink-muted">
                  {s.type} · {fmtRelTime(s.created_at)}
                </p>
              </div>
              <a
                href={s.url}
                target="_blank"
                rel="noreferrer"
                className="rounded-md p-1 text-ink-muted hover:bg-bg-surface hover:text-ink"
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </li>
          ))}
        </ul>
      </CardBody>
    </Card>
  );
}
