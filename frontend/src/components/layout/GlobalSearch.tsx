import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Search, FileText, Globe, Briefcase, Loader2 } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { globalSearch } from "@/api/endpoints";
import { Badge, statusTone } from "@/components/ui/Badge";
import { cn } from "@/lib/cn";
import type {
  SearchFileHit,
  SearchSourceHit,
  SearchJobHit,
} from "@/types/api";

function useDebounce(value: string, ms = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

export function GlobalSearch() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debouncedQ = useDebounce(q, 300);

  const { data, isFetching } = useQuery({
    queryKey: ["globalSearch", debouncedQ],
    queryFn: () => globalSearch(debouncedQ),
    enabled: debouncedQ.trim().length >= 2,
    staleTime: 60_000,
  });

  const hasResults =
    data &&
    (data.files.items.length > 0 ||
      data.sources.items.length > 0 ||
      data.jobs.items.length > 0);

  const showDropdown = open && debouncedQ.trim().length >= 2;

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const go = useCallback(
    (path: string) => {
      navigate(path);
      setOpen(false);
      setQ("");
    },
    [navigate],
  );

  return (
    <div ref={wrapperRef} className="relative w-full max-w-xl">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder="Search files, sources, jobs…"
          className="h-10 w-full rounded-lg border border-line bg-bg-muted pl-10 pr-9 text-sm text-ink placeholder:text-ink-faint focus:border-ink-soft focus:bg-bg-surface focus:outline-none focus:ring-2 focus:ring-ink/10"
          aria-label="Global search"
          aria-expanded={showDropdown}
          aria-haspopup="listbox"
          role="combobox"
          aria-autocomplete="list"
        />
        {isFetching && (
          <div className="absolute right-3 top-0 flex h-10 items-center">
            <Loader2 className="h-4 w-4 animate-spin text-ink-faint" />
          </div>
        )}
      </div>

      {showDropdown && (
        <div
          className="absolute left-0 right-0 top-full z-50 mt-1 max-h-[420px] overflow-y-auto rounded-lg border border-line bg-bg-surface shadow-lg"
          role="listbox"
        >
          {!data && isFetching && (
            <p className="px-4 py-6 text-center text-sm text-ink-muted">Searching…</p>
          )}

          {data && !hasResults && (
            <p className="px-4 py-6 text-center text-sm text-ink-muted">
              No results for "<span className="font-medium text-ink">{data.q}</span>"
            </p>
          )}

          {data && hasResults && (
            <>
              {data.files.items.length > 0 && (
                <ResultSection
                  icon={FileText}
                  label="Files"
                  count={data.files.total}
                >
                  {data.files.items.map((f) => (
                    <FileRow key={f.id} hit={f} onClick={() => go(`/knowledge-library/${f.id}`)} />
                  ))}
                </ResultSection>
              )}

              {data.sources.items.length > 0 && (
                <ResultSection
                  icon={Globe}
                  label="Sources"
                  count={data.sources.total}
                >
                  {data.sources.items.map((s) => (
                    <SourceRow key={s.id} hit={s} onClick={() => go(`/search-operations?source=${s.id}`)} />
                  ))}
                </ResultSection>
              )}

              {data.jobs.items.length > 0 && (
                <ResultSection
                  icon={Briefcase}
                  label="Jobs"
                  count={data.jobs.total}
                >
                  {data.jobs.items.map((j) => (
                    <JobRow key={j.id} hit={j} onClick={() => go(`/discovery-tools?job=${j.id}`)} />
                  ))}
                </ResultSection>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

/* ---- Sub-components ---- */

function ResultSection({
  icon: Icon,
  label,
  count,
  children,
}: {
  icon: React.ElementType;
  label: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <div className="border-b border-line last:border-b-0">
      <div className="flex items-center gap-2 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
        <Icon className="h-3.5 w-3.5" />
        {label}
        <span className="ml-auto text-[10px] font-normal normal-case text-ink-faint">
          {count} total
        </span>
      </div>
      <ul>{children}</ul>
    </div>
  );
}

const rowBase =
  "flex cursor-pointer items-center gap-3 px-4 py-2 text-sm hover:bg-bg-muted transition-colors";

function FileRow({ hit, onClick }: { hit: SearchFileHit; onClick: () => void }) {
  return (
    <li className={rowBase} onClick={onClick} role="option" aria-selected={false}>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-ink">{hit.title}</p>
        {hit.tags.length > 0 && (
          <p className="truncate text-xs text-ink-faint">{hit.tags.join(", ")}</p>
        )}
      </div>
      <Badge tone={statusTone(hit.status)}>{hit.status.replace("_", " ")}</Badge>
    </li>
  );
}

function SourceRow({ hit, onClick }: { hit: SearchSourceHit; onClick: () => void }) {
  return (
    <li className={rowBase} onClick={onClick} role="option" aria-selected={false}>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-ink">{hit.url}</p>
        <p className="text-xs text-ink-faint">
          {[hit.brand, hit.region].filter(Boolean).join(" · ") || "—"}
        </p>
      </div>
    </li>
  );
}

function JobRow({ hit, onClick }: { hit: SearchJobHit; onClick: () => void }) {
  return (
    <li className={rowBase} onClick={onClick} role="option" aria-selected={false}>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-ink">{hit.source_label}</p>
        {hit.brand && <p className="text-xs text-ink-faint">{hit.brand}</p>}
      </div>
      <Badge tone={statusTone(hit.status)}>{hit.status}</Badge>
    </li>
  );
}
