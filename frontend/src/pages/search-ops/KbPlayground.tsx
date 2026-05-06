import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  Send,
  Square,
  RefreshCw,
  ExternalLink,
  Sparkles,
  Search as SearchIcon,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import { errorWithRef } from "@/lib/errorRef";
import { useToast } from "@/contexts/ToastContext";
import { kbSync } from "@/api/endpoints";
import { streamKbChat, streamKbSearch } from "@/api/kbStream";
import type { KbChatSource, KbSearchResult, KbTarget } from "@/types/api";

type Mode = "search" | "chat";

interface ChatTurn {
  id: string;
  user: string;
  answer: string;
  sources: KbChatSource[];
  done: boolean;
  error?: string;
}

// NOTE: Chat transcript lives in component state only — resets on route change / unmount.
// To persist properly we would either:
//   a) lift into a store (Zustand/Context) scoped to the session, or
//   b) add a backend conversation store (POST /kb/chat/sessions, GET /kb/chat/sessions/:id)
//      so transcripts survive reloads and multi-device.
// (b) is the right long-term answer — (a) is fine as an interim step.

export default function KbPlayground() {
  const toast = useToast();
  const [mode, setMode] = useState<Mode>("search");
  const [kbTarget] = useState<KbTarget>("public"); // only public exposed for now
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(10);

  // Search state
  const [searchResults, setSearchResults] = useState<KbSearchResult[]>([]);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchTotal, setSearchTotal] = useState<number | null>(null);

  // Chat state
  const [turns, setTurns] = useState<ChatTurn[]>([]);

  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const stopStream = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  };

  const runSearch = async () => {
    if (!query.trim() || streaming) return;
    setSearchResults([]);
    setSearchError(null);
    setSearchTotal(null);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setStreaming(true);
    try {
      await streamKbSearch(
        { query, kb_target: kbTarget, limit },
        {
          onResult: (r) => setSearchResults((prev) => [...prev, r]),
          onError: (msg) => setSearchError(msg),
          onComplete: (total) => setSearchTotal(total),
        },
        ctrl.signal,
      );
    } catch (e) {
      if (!ctrl.signal.aborted) {
        const msg = e instanceof Error ? e.message : "Search failed";
        setSearchError(msg);
        toast.error("KB search failed", errorWithRef(e, "Search failed"));
      }
    } finally {
      if (abortRef.current === ctrl) abortRef.current = null;
      setStreaming(false);
    }
  };

  const runChat = async () => {
    if (!query.trim() || streaming) return;
    const turnId = `t-${Date.now()}`;
    const userText = query;
    setTurns((prev) => [
      ...prev,
      { id: turnId, user: userText, answer: "", sources: [], done: false },
    ]);
    setQuery("");

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setStreaming(true);
    try {
      await streamKbChat(
        { query: userText, kb_target: kbTarget, context_limit: 5 },
        {
          onSources: (sources) =>
            setTurns((prev) =>
              prev.map((t) => (t.id === turnId ? { ...t, sources } : t)),
            ),
          onToken: (text) =>
            setTurns((prev) =>
              prev.map((t) =>
                t.id === turnId ? { ...t, answer: t.answer + text } : t,
              ),
            ),
          onError: (msg) =>
            setTurns((prev) =>
              prev.map((t) =>
                t.id === turnId ? { ...t, error: msg, done: true } : t,
              ),
            ),
          onComplete: () =>
            setTurns((prev) =>
              prev.map((t) => (t.id === turnId ? { ...t, done: true } : t)),
            ),
        },
        ctrl.signal,
      );
    } catch (e) {
      if (!ctrl.signal.aborted) {
        const msg = e instanceof Error ? e.message : "Chat failed";
        setTurns((prev) =>
          prev.map((t) =>
            t.id === turnId ? { ...t, error: msg, done: true } : t,
          ),
        );
        toast.error("KB chat failed", errorWithRef(e, "Chat failed"));
      }
    } finally {
      if (abortRef.current === ctrl) abortRef.current = null;
      setStreaming(false);
    }
  };

  const submit = () => {
    if (mode === "search") runSearch();
    else runChat();
  };

  const syncMut = useMutation({
    mutationFn: kbSync,
    onSuccess: (res) =>
      toast.success("KB re-index started", `Job ${res.ingestion_job_id}`),
    onError: (e: unknown) => {
      toast.error("KB re-index failed", errorWithRef(e, "Sync failed"));
    },
  });

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1 rounded-lg border border-line bg-bg-muted p-1">
          <ModeButton active={mode === "search"} onClick={() => setMode("search")}>
            <SearchIcon className="h-3.5 w-3.5" /> Search
          </ModeButton>
          <ModeButton active={mode === "chat"} onClick={() => setMode("chat")}>
            <Sparkles className="h-3.5 w-3.5" /> Chat
          </ModeButton>
        </div>

        <div className="text-xs text-ink-muted">
          KB target: <span className="font-medium text-ink">{kbTarget}</span>
        </div>

        {mode === "search" && (
          <label className="flex items-center gap-2 text-xs text-ink-muted">
            Limit
            <input
              type="number"
              min={1}
              max={50}
              value={limit}
              onChange={(e) => setLimit(Math.max(1, Math.min(50, Number(e.target.value) || 1)))}
              className="h-8 w-16 rounded-md border border-line bg-bg-surface px-2 text-sm text-ink"
            />
          </label>
        )}

        <div className="ml-auto">
          <Button
            variant="outline"
            size="sm"
            disabled={syncMut.isPending}
            onClick={() => syncMut.mutate()}
          >
            <RefreshCw className={cn("h-3.5 w-3.5", syncMut.isPending && "animate-spin")} />
            {syncMut.isPending ? "Re-indexing…" : "Re-index KB"}
          </Button>
        </div>
      </div>

      <Card>
        <CardBody>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
            className="flex items-center gap-2"
          >
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={
                mode === "search"
                  ? "Search the KB — e.g. 'damage waiver policy'"
                  : "Ask the KB — e.g. 'how do I extend a rental?'"
              }
              className="h-11 w-full rounded-lg border border-line bg-bg-surface px-4 text-sm text-ink placeholder:text-ink-faint focus:border-ink-soft focus:outline-none focus:ring-2 focus:ring-ink/10"
              disabled={streaming}
            />
            {streaming ? (
              <Button type="button" variant="outline" onClick={stopStream}>
                <Square className="h-4 w-4" /> Stop
              </Button>
            ) : (
              <Button type="submit" variant="primary" disabled={!query.trim()}>
                <Send className="h-4 w-4" /> {mode === "search" ? "Search" : "Ask"}
              </Button>
            )}
          </form>
        </CardBody>
      </Card>

      <div className="mt-4">
        {mode === "search" ? (
          <SearchResults
            streaming={streaming}
            results={searchResults}
            error={searchError}
            total={searchTotal}
          />
        ) : (
          <ChatTranscript turns={turns} streaming={streaming} />
        )}
      </div>
    </>
  );
}

function ModeButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
        active ? "bg-bg-surface text-ink shadow-sm" : "text-ink-muted hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}

function SearchResults({
  streaming,
  results,
  error,
  total,
}: {
  streaming: boolean;
  results: KbSearchResult[];
  error: string | null;
  total: number | null;
}) {
  if (error) {
    return (
      <Card>
        <CardBody>
          <p className="text-sm text-status-err">Error: {error}</p>
        </CardBody>
      </Card>
    );
  }
  if (!streaming && results.length === 0 && total === null) {
    return (
      <p className="px-2 py-8 text-center text-sm text-ink-muted">
        Run a query to see semantic matches from the KB.
      </p>
    );
  }
  if (!streaming && results.length === 0 && total === 0) {
    return (
      <p className="px-2 py-8 text-center text-sm text-ink-muted">No matches.</p>
    );
  }
  return (
    <div className="space-y-3">
      {results.map((r) => (
        <Card key={`${r.rank}-${r.s3_uri ?? r.title}`}>
          <CardBody>
            <div className="mb-1 flex items-start gap-3">
              <span className="mt-0.5 shrink-0 rounded bg-bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-ink-muted tabular-nums">
                #{r.rank}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-ink">{r.title}</p>
                <p className="text-[11px] text-ink-faint tabular-nums">
                  score {r.score.toFixed(3)}
                </p>
              </div>
              {r.source_url && (
                <a
                  href={r.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-ink-muted hover:text-ink"
                >
                  source <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
            <p className="whitespace-pre-wrap text-sm text-ink-soft">{r.snippet}</p>
          </CardBody>
        </Card>
      ))}
      {streaming && (
        <p className="px-2 py-2 text-xs text-ink-muted">Streaming results…</p>
      )}
      {!streaming && total !== null && (
        <p className="px-2 py-2 text-xs text-ink-faint">
          {total} result{total === 1 ? "" : "s"} total.
        </p>
      )}
    </div>
  );
}

function ChatTranscript({
  turns,
  streaming,
}: {
  turns: ChatTurn[];
  streaming: boolean;
}) {
  if (turns.length === 0) {
    return (
      <p className="px-2 py-8 text-center text-sm text-ink-muted">
        Ask a question to see a streamed answer with citations.
      </p>
    );
  }
  return (
    <div className="space-y-4">
      {turns.map((t, i) => (
        <ChatTurnView
          key={t.id}
          turn={t}
          isLast={i === turns.length - 1}
          streaming={streaming}
        />
      ))}
    </div>
  );
}

function ChatTurnView({
  turn,
  isLast,
  streaming,
}: {
  turn: ChatTurn;
  isLast: boolean;
  streaming: boolean;
}) {
  const [openCites, setOpenCites] = useState(false);
  const pending = isLast && streaming && !turn.done;
  const awaitingAnswer = pending && !turn.answer;

  return (
    <div className="space-y-2">
      <div className="rounded-lg border border-line bg-bg-muted px-4 py-2 text-sm text-ink">
        <span className="mr-2 text-[10px] font-semibold uppercase tracking-wide text-ink-muted">
          you
        </span>
        {turn.user}
      </div>

      <div className="rounded-lg border border-line bg-bg-surface px-4 py-3 text-sm text-ink">
        <span className="mr-2 text-[10px] font-semibold uppercase tracking-wide text-ink-muted">
          kb
        </span>
        {turn.error ? (
          <span className="text-status-err">Error: {turn.error}</span>
        ) : awaitingAnswer ? (
          <span className="inline-flex items-center gap-2 text-ink-muted">
            <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-ink-muted border-t-transparent" />
            Thinking…
          </span>
        ) : (
          <span className="whitespace-pre-wrap">{turn.answer}</span>
        )}

        {turn.sources.length > 0 && (
          <div className="mt-3 border-t border-line pt-2">
            <button
              onClick={() => setOpenCites((v) => !v)}
              className="inline-flex items-center gap-1 text-xs font-medium text-ink-muted hover:text-ink"
            >
              {openCites ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
              Citations ({turn.sources.length})
            </button>
            {openCites && (
              <ul className="mt-2 space-y-2">
                {turn.sources.map((s, idx) => (
                  <li
                    key={idx}
                    className="rounded border border-line-soft bg-bg-muted px-3 py-2 text-xs"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-medium text-ink">{s.title}</span>
                      {s.url && (
                        <a
                          href={s.url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex shrink-0 items-center gap-1 text-ink-muted hover:text-ink"
                        >
                          open <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </div>
                    <p className="mt-1 text-ink-soft">{s.snippet}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
