import { useState, useRef, useEffect, useCallback } from "react";
import {
  Sparkles,
  Wand2,
  FileText,
  CheckCircle,
  RefreshCw,
  ArrowRight,
  Copy,
  Check,
  ChevronDown,
  Loader2,
  MessageSquare,
  Lightbulb,
  Scissors,
  Expand,
  ShieldCheck,
  Languages,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { uuid } from "@/lib/uuid";

// ---------------------------------------------------------------------------
// Mock AI response generator — simulates streaming text
// ---------------------------------------------------------------------------
type ActionId =
  | "rewrite-formal"
  | "rewrite-casual"
  | "rewrite-concise"
  | "expand"
  | "summarize"
  | "grammar"
  | "outline"
  | "translate-es"
  | "translate-fr"
  | "compliance"
  | "custom";

interface QuickAction {
  id: ActionId;
  label: string;
  icon: React.ReactNode;
  group: string;
  description: string;
}

const ic = "h-3.5 w-3.5";

const QUICK_ACTIONS: QuickAction[] = [
  { id: "rewrite-formal", label: "Formal tone", icon: <Wand2 className={ic} />, group: "Rewrite", description: "Rewrite in a professional, formal tone" },
  { id: "rewrite-casual", label: "Casual tone", icon: <MessageSquare className={ic} />, group: "Rewrite", description: "Rewrite in a friendly, conversational tone" },
  { id: "rewrite-concise", label: "Make concise", icon: <Scissors className={ic} />, group: "Rewrite", description: "Shorten while keeping key information" },
  { id: "expand", label: "Expand", icon: <Expand className={ic} />, group: "Generate", description: "Add more detail and depth" },
  { id: "summarize", label: "Summarize", icon: <FileText className={ic} />, group: "Generate", description: "Create a brief summary" },
  { id: "outline", label: "Generate outline", icon: <Lightbulb className={ic} />, group: "Generate", description: "Create a structured outline from the content" },
  { id: "grammar", label: "Fix grammar", icon: <CheckCircle className={ic} />, group: "Polish", description: "Fix grammar, spelling, and punctuation" },
  { id: "compliance", label: "Compliance check", icon: <ShieldCheck className={ic} />, group: "Polish", description: "Flag potential compliance or brand-voice issues" },
  { id: "translate-es", label: "→ Spanish", icon: <Languages className={ic} />, group: "Translate", description: "Translate content to Spanish" },
  { id: "translate-fr", label: "→ French", icon: <Languages className={ic} />, group: "Translate", description: "Translate content to French" },
];

const GROUPS = [...new Set(QUICK_ACTIONS.map((a) => a.group))];

// ---------------------------------------------------------------------------
// Mock response bank — keyed by action, returns plausible AI output
// ---------------------------------------------------------------------------
function getMockResponse(action: ActionId, body: string, customPrompt?: string): string {
  const snippet = body.slice(0, 120).replace(/\n/g, " ").trim();
  const wordCount = body.trim().split(/\s+/).length;

  const responses: Record<ActionId, string> = {
    "rewrite-formal": `## Formal Rewrite\n\nWe are pleased to present the following revised content, crafted in a professional and authoritative tone suitable for corporate communications.\n\n---\n\n${snippet ? `Based on your content regarding "${snippet.slice(0, 60)}…", here is the formal version:\n\n` : ""}Dear Valued Stakeholder,\n\nPlease find below the revised documentation that has been carefully restructured to align with our corporate communication standards. The content maintains all factual accuracy while adopting a tone appropriate for executive-level distribution.\n\nKey modifications include:\n- Replacement of colloquial expressions with formal equivalents\n- Restructured sentence patterns for clarity and authority\n- Added transitional phrases for improved document flow\n\n*This is a mock AI response. In production, the actual content would be rewritten here.*`,

    "rewrite-casual": `## Casual Rewrite ✨\n\nHey! Here's a friendlier take on your content:\n\n${snippet ? `So you were talking about "${snippet.slice(0, 50)}…" — ` : ""}here's how we'd say it in a more relaxed way:\n\nLook, the gist is pretty simple. We've taken all the important bits from your article and wrapped them in language that feels more like a conversation than a textbook. Think of it as explaining this to a colleague over coffee.\n\nThe key points are still there — we just made them easier to digest. No jargon walls, no corporate-speak. Just clear, friendly info that gets the job done.\n\n*This is a mock AI response. Connect to your LLM backend to get real rewrites.*`,

    "rewrite-concise": `## Concise Version\n\n${snippet ? `Original: ~${wordCount} words → Reduced to ~${Math.round(wordCount * 0.4)} words\n\n` : ""}${snippet ? `**"${snippet.slice(0, 80)}…"**\n\n` : ""}Key points distilled:\n\n- Core message preserved, filler removed\n- Redundant qualifiers eliminated\n- Passive voice converted to active\n- ${Math.round(wordCount * 0.6)} words cut without losing meaning\n\n*Mock response — real concise rewrite would appear here.*`,

    expand: `## Expanded Content\n\n${snippet ? `Building on your content about "${snippet.slice(0, 60)}…":\n\n` : ""}### Additional Context\n\nThe topic warrants deeper exploration across several dimensions. Below is an expanded treatment that adds supporting detail, examples, and context.\n\n### Background\nUnderstanding the historical context helps frame why this information matters to our audience. The rental car industry has evolved significantly, and customers increasingly expect self-service knowledge access.\n\n### Detailed Breakdown\n1. **Primary considerations** — The core facts your audience needs, presented with supporting evidence\n2. **Edge cases** — Scenarios that aren't immediately obvious but come up frequently in customer interactions\n3. **Related topics** — Adjacent information that adds value and reduces follow-up questions\n\n### Practical Examples\n- Example scenario A: A customer calls about a specific situation…\n- Example scenario B: A branch agent needs to quickly reference…\n\n*Mock expansion — ${Math.round(wordCount * 2.5)} words target. Real AI would generate contextual content.*`,

    summarize: `## Summary\n\n${snippet ? `**Source:** "${snippet.slice(0, 80)}…" (${wordCount} words)\n\n` : ""}**TL;DR:** ${snippet ? `This article covers ${snippet.slice(0, 100)}. ` : ""}The content addresses key operational procedures and customer-facing information relevant to the ABG knowledge base.\n\n**Key Takeaways:**\n- Primary topic identified and distilled\n- ${Math.max(3, Math.round(wordCount / 80))} main sections condensed\n- Action items and critical details preserved\n- Supporting context summarized\n\n**Recommended audience:** Customer care agents, branch operations\n\n*Mock summary — real AI would produce a contextual summary of your ${wordCount}-word article.*`,

    outline: `## Generated Outline\n\n${snippet ? `Based on: "${snippet.slice(0, 60)}…"\n\n` : ""}### Suggested Structure\n\n1. **Introduction**\n   - Hook / context setter\n   - Scope of the article\n   - Who this is for\n\n2. **Core Information**\n   - Primary policy or procedure details\n   - Step-by-step instructions (if applicable)\n   - Key terms and definitions\n\n3. **Common Scenarios**\n   - Scenario A: Standard case\n   - Scenario B: Exception handling\n   - Scenario C: Escalation path\n\n4. **FAQ Section**\n   - Top 3-5 questions customers ask\n   - Clear, concise answers\n\n5. **Related Resources**\n   - Links to related articles\n   - Contact information for further help\n\n6. **Revision History**\n   - Last updated date\n   - Change summary\n\n*Mock outline — real AI would analyze your content and suggest a tailored structure.*`,

    grammar: `## Grammar & Style Review\n\n${snippet ? `Analyzed: "${snippet.slice(0, 60)}…" (${wordCount} words)\n\n` : ""}### Issues Found: 7\n\n| # | Type | Location | Suggestion |\n|---|------|----------|------------|\n| 1 | Spelling | Para 2 | "recieve" → "receive" |\n| 2 | Grammar | Para 1 | Subject-verb agreement: "data are" → "data is" |\n| 3 | Punctuation | Para 3 | Missing comma after introductory clause |\n| 4 | Style | Para 1 | Passive voice → consider active |\n| 5 | Clarity | Para 4 | Ambiguous pronoun "it" — specify referent |\n| 6 | Consistency | Throughout | Mixed use of "customer" and "client" |\n| 7 | Readability | Para 2 | Sentence too long (42 words) — consider splitting |\n\n**Readability Score:** 68/100 (Grade 9 level)\n**Suggested Score After Fixes:** 82/100 (Grade 7 level)\n\n*Mock grammar check — real AI would analyze your actual content.*`,

    compliance: `## Compliance Review 🛡️\n\n${snippet ? `Scanned: "${snippet.slice(0, 60)}…"\n\n` : ""}### Brand Voice Alignment: 87%\n\n### Flags\n\n⚠️ **Potential Issues (3)**\n\n1. **Pricing mention (Para 2)** — Avoid specific dollar amounts in knowledge articles. Reference the pricing page instead.\n2. **Competitor reference (Para 4)** — Indirect mention of competitor detected. Recommend neutral language per brand guidelines.\n3. **Legal disclaimer missing** — Articles about insurance/waiver topics require the standard legal footer.\n\n✅ **Passed Checks (5)**\n- Brand name usage is consistent\n- Tone matches corporate guidelines\n- No PII detected in content\n- Accessibility language is inclusive\n- Regional terminology is appropriate\n\n*Mock compliance scan — real AI would check against your brand rulebook.*`,

    "translate-es": `## Traducción al Español\n\n${snippet ? `**Original:** "${snippet.slice(0, 60)}…"\n\n` : ""}---\n\nEstimado cliente,\n\nA continuación encontrará la información traducida al español. Esta traducción mantiene el significado original y ha sido adaptada para el público hispanohablante.\n\nLos puntos principales incluyen:\n- Información completa sobre políticas y procedimientos\n- Instrucciones paso a paso cuando corresponda\n- Datos de contacto para asistencia adicional\n\n*Traducción simulada — conecte su backend de IA para traducciones reales.*\n\n**Nota:** Se recomienda revisión por un hablante nativo antes de publicar.`,

    "translate-fr": `## Traduction en Français\n\n${snippet ? `**Original :** « ${snippet.slice(0, 60)}… »\n\n` : ""}---\n\nCher client,\n\nVeuillez trouver ci-dessous les informations traduites en français. Cette traduction conserve le sens original et a été adaptée pour le public francophone.\n\nLes points principaux comprennent :\n- Informations complètes sur les politiques et procédures\n- Instructions étape par étape le cas échéant\n- Coordonnées pour une assistance supplémentaire\n\n*Traduction simulée — connectez votre backend IA pour des traductions réelles.*\n\n**Note :** Une révision par un locuteur natif est recommandée avant publication.`,

    custom: `## AI Response\n\n${customPrompt ? `**Your prompt:** "${customPrompt}"\n\n` : ""}${snippet ? `**Context:** "${snippet.slice(0, 80)}…"\n\n` : ""}---\n\nBased on your request, here's what I'd suggest:\n\nThe content has been analyzed and processed according to your instructions. In a production environment, this would be a fully contextual response generated by your connected LLM.\n\nKey observations:\n- The article is ${wordCount} words long\n- Content appears to be ${wordCount > 200 ? "detailed" : "brief"}\n- Tone is currently ${wordCount > 100 ? "informational" : "introductory"}\n\n*Mock response — connect your AI backend for real custom prompts.*`,
  };

  return responses[action] ?? responses.custom;
}

// ---------------------------------------------------------------------------
// Chat history types
// ---------------------------------------------------------------------------
interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  action?: ActionId;
  timestamp: number;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
interface AIAssistantPanelProps {
  articleBody: string;
  onInsert: (text: string) => void;
  className?: string;
}

export function AIAssistantPanel({ articleBody, onInsert, className }: AIAssistantPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [customPrompt, setCustomPrompt] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamedText, setStreamedText] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [expandedGroup, setExpandedGroup] = useState<string | null>("Rewrite");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll chat
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streamedText]);

  const simulateStream = useCallback(
    (fullText: string, action: ActionId, userLabel: string) => {
      // Add user message
      const userId = uuid();
      const userMsg: ChatMessage = {
        id: userId,
        role: "user",
        content: userLabel,
        action,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setStreaming(true);
      setStreamedText("");

      // Simulate token-by-token streaming
      const words = fullText.split(" ");
      let idx = 0;
      const interval = setInterval(() => {
        const chunk = Math.min(idx + 3, words.length); // 3 words at a time
        setStreamedText(words.slice(0, chunk).join(" "));
        idx = chunk;
        if (idx >= words.length) {
          clearInterval(interval);
          const assistantMsg: ChatMessage = {
            id: uuid(),
            role: "assistant",
            content: fullText,
            action,
            timestamp: Date.now(),
          };
          setMessages((prev) => [...prev, assistantMsg]);
          setStreamedText("");
          setStreaming(false);
        }
      }, 30);
    },
    [],
  );

  const runAction = useCallback(
    (action: ActionId, label: string, prompt?: string) => {
      if (streaming) return;
      const response = getMockResponse(action, articleBody, prompt);
      simulateStream(response, action, label);
    },
    [articleBody, streaming, simulateStream],
  );

  const handleCustomSubmit = () => {
    const prompt = customPrompt.trim();
    if (!prompt || streaming) return;
    setCustomPrompt("");
    runAction("custom", prompt, prompt);
  };

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const clearChat = () => {
    setMessages([]);
    setStreamedText("");
  };

  return (
    <div className={cn("flex flex-col rounded-xl border border-line bg-bg-surface shadow-card", className)}>
      {/* Header */}
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="grid h-7 w-7 place-items-center rounded-lg bg-brand-soft">
            <Sparkles className="h-3.5 w-3.5 text-brand" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-ink">AI Assistant</h3>
            <p className="text-[10px] text-ink-muted">Mock mode — not connected to backend</p>
          </div>
        </div>
        {messages.length > 0 && (
          <button
            onClick={clearChat}
            className="rounded-md p-1 text-ink-faint hover:bg-bg-muted hover:text-ink-muted"
            title="Clear chat"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Quick actions */}
      <div className="border-b border-line px-3 py-2">
        <div className="space-y-1">
          {GROUPS.map((group) => {
            const actions = QUICK_ACTIONS.filter((a) => a.group === group);
            const isOpen = expandedGroup === group;
            return (
              <div key={group}>
                <button
                  onClick={() => setExpandedGroup(isOpen ? null : group)}
                  className="flex w-full items-center justify-between rounded-md px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-ink-muted hover:bg-bg-muted"
                >
                  {group}
                  <ChevronDown
                    className={cn("h-3 w-3 transition-transform", isOpen && "rotate-180")}
                  />
                </button>
                {isOpen && (
                  <div className="mt-0.5 grid grid-cols-2 gap-1 pb-1">
                    {actions.map((a) => (
                      <button
                        key={a.id}
                        disabled={streaming}
                        onClick={() => runAction(a.id, a.label)}
                        title={a.description}
                        className={cn(
                          "flex items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-[11px] font-medium transition-colors",
                          "text-ink-soft hover:bg-bg-muted hover:text-ink",
                          streaming && "opacity-50 cursor-not-allowed",
                        )}
                      >
                        {a.icon}
                        {a.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Chat area */}
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-3 py-3" style={{ maxHeight: "22rem" }}>
        {messages.length === 0 && !streaming && (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <Sparkles className="mb-2 h-8 w-8 text-ink-faint" />
            <p className="text-xs font-medium text-ink-muted">
              Select an action above or type a custom prompt
            </p>
            <p className="mt-1 text-[10px] text-ink-faint">
              AI will use your article content as context
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={cn(
              "rounded-lg px-3 py-2 text-xs leading-relaxed",
              msg.role === "user"
                ? "ml-6 bg-brand-soft text-brand"
                : "mr-2 border border-line-soft bg-bg-muted text-ink-soft",
            )}
          >
            {msg.role === "user" ? (
              <div className="flex items-center gap-1.5">
                <ArrowRight className="h-3 w-3" />
                <span className="font-medium">{msg.content}</span>
              </div>
            ) : (
              <>
                <div className="whitespace-pre-wrap">{msg.content}</div>
                <div className="mt-2 flex items-center gap-1 border-t border-line-soft pt-2">
                  <button
                    onClick={() => handleCopy(msg.id, msg.content)}
                    className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-ink-muted hover:bg-bg-surface hover:text-ink"
                  >
                    {copiedId === msg.id ? (
                      <Check className="h-3 w-3 text-status-ok" />
                    ) : (
                      <Copy className="h-3 w-3" />
                    )}
                    {copiedId === msg.id ? "Copied" : "Copy"}
                  </button>
                  <button
                    onClick={() => onInsert(msg.content)}
                    className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-ink-muted hover:bg-bg-surface hover:text-ink"
                  >
                    <FileText className="h-3 w-3" />
                    Insert into editor
                  </button>
                  <button
                    onClick={() => runAction(msg.action ?? "custom", `Regenerate: ${msg.action}`, undefined)}
                    className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-ink-muted hover:bg-bg-surface hover:text-ink"
                  >
                    <RefreshCw className="h-3 w-3" />
                    Retry
                  </button>
                </div>
              </>
            )}
          </div>
        ))}

        {/* Streaming indicator */}
        {streaming && (
          <div className="mr-2 rounded-lg border border-line-soft bg-bg-muted px-3 py-2 text-xs leading-relaxed text-ink-soft">
            <div className="whitespace-pre-wrap">{streamedText}</div>
            <div className="mt-1 flex items-center gap-1 text-[10px] text-ink-faint">
              <Loader2 className="h-3 w-3 animate-spin" />
              Generating…
            </div>
          </div>
        )}
      </div>

      {/* Custom prompt input */}
      <div className="border-t border-line px-3 py-2">
        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={customPrompt}
            onChange={(e) => setCustomPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleCustomSubmit();
              }
            }}
            placeholder="Ask AI anything about your article…"
            rows={1}
            className="flex-1 resize-none rounded-lg border border-line bg-bg-surface px-3 py-2 text-xs text-ink placeholder:text-ink-faint focus:border-ink-soft focus:outline-none focus:ring-2 focus:ring-ink/10"
          />
          <Button
            variant="primary"
            size="sm"
            disabled={!customPrompt.trim() || streaming}
            onClick={handleCustomSubmit}
          >
            <Sparkles className="h-3.5 w-3.5" />
          </Button>
        </div>
        <p className="mt-1 text-[10px] text-ink-faint">
          Press Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}
