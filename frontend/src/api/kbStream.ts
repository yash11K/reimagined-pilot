import { sseUrl } from "./client";
import type {
  KbChatRequest,
  KbChatSource,
  KbSearchRequest,
  KbSearchResult,
} from "@/types/api";

// POST-based SSE: fetch streaming body, parse `event:`/`data:` frames.
// Native EventSource only supports GET, so we roll our own for KB endpoints.

type Frame = { event: string; data: string };

async function* parseSseFrames(
  res: Response,
  signal: AbortSignal,
): AsyncGenerator<Frame> {
  if (!res.body) return;
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  try {
    while (!signal.aborted) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      let idx: number;
      while ((idx = buf.indexOf("\n\n")) !== -1) {
        const raw = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const frame = parseFrame(raw);
        if (frame) yield frame;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseFrame(raw: string): Frame | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

async function postStream(path: string, body: unknown, signal: AbortSignal) {
  const res = await fetch(sseUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    throw new Error(`${path} ${res.status} ${res.statusText}`);
  }
  return res;
}

export interface KbSearchHandlers {
  onResult: (r: KbSearchResult) => void;
  onError: (msg: string) => void;
  onComplete: (total: number) => void;
}

export async function streamKbSearch(
  body: KbSearchRequest,
  handlers: KbSearchHandlers,
  signal: AbortSignal,
): Promise<void> {
  const res = await postStream("/kb/search", body, signal);
  for await (const frame of parseSseFrames(res, signal)) {
    if (signal.aborted) return;
    const payload = safeJson(frame.data);
    switch (frame.event) {
      case "result":
        handlers.onResult(payload as KbSearchResult);
        break;
      case "error":
        handlers.onError(
          (payload as { error?: string })?.error ?? "Unknown error",
        );
        break;
      case "search_complete":
        handlers.onComplete(
          Number((payload as { total_results?: number })?.total_results ?? 0),
        );
        break;
    }
  }
}

export interface KbChatHandlers {
  onSources: (sources: KbChatSource[]) => void;
  onToken: (text: string) => void;
  onError: (msg: string) => void;
  onComplete: () => void;
}

export async function streamKbChat(
  body: KbChatRequest,
  handlers: KbChatHandlers,
  signal: AbortSignal,
): Promise<void> {
  const res = await postStream("/kb/chat", body, signal);
  for await (const frame of parseSseFrames(res, signal)) {
    if (signal.aborted) return;
    const payload = safeJson(frame.data);
    switch (frame.event) {
      case "sources":
        handlers.onSources(
          ((payload as { sources?: KbChatSource[] })?.sources ?? []),
        );
        break;
      case "token":
        handlers.onToken((payload as { text?: string })?.text ?? "");
        break;
      case "error":
        handlers.onError(
          (payload as { error?: string })?.error ?? "Unknown error",
        );
        break;
      case "chat_complete":
        handlers.onComplete();
        break;
    }
  }
}

function safeJson(s: string): unknown {
  try {
    return JSON.parse(s);
  } catch {
    return {};
  }
}
