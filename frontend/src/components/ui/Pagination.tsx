import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/cn";

interface Props {
  page: number;
  size: number;
  total: number;
  onPage: (p: number) => void;
}

export function Pagination({ page, size, total, onPage }: Props) {
  const pages = Math.max(1, Math.ceil(total / size));
  const start = total === 0 ? 0 : (page - 1) * size + 1;
  const end = Math.min(page * size, total);
  const canPrev = page > 1;
  const canNext = page < pages;

  return (
    <div className="flex items-center justify-between border-t border-line px-5 py-3 text-xs text-ink-muted">
      <span>
        {start}–{end} of {total}
      </span>
      <div className="flex items-center gap-1">
        <button
          disabled={!canPrev}
          onClick={() => onPage(page - 1)}
          className={cn(
            "inline-flex h-7 items-center gap-1 rounded-md border border-line px-2 font-medium",
            canPrev ? "text-ink hover:bg-bg-muted" : "cursor-not-allowed text-ink-faint"
          )}
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          Prev
        </button>
        <span className="px-2 font-medium text-ink">
          {page} / {pages}
        </span>
        <button
          disabled={!canNext}
          onClick={() => onPage(page + 1)}
          className={cn(
            "inline-flex h-7 items-center gap-1 rounded-md border border-line px-2 font-medium",
            canNext ? "text-ink hover:bg-bg-muted" : "cursor-not-allowed text-ink-faint"
          )}
        >
          Next
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
