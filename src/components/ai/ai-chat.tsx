import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Bot, Send, Sparkles, Mic, ImagePlus, FileUp, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { PixelBadge, PixelSprite, SPRITES } from "@/components/pixel/pixel-art";
import { apiPost, ApiError } from "@/lib/api-client";

// One example per implemented route (docs/query-router.md) so the three
// backend cases are easy to try from the UI.
const aiSuggestions = [
  "What is my next class?",
  "What are the attendance requirements?",
  "Which faculty work in NLP and when can I meet them?",
];

type Route = "structured" | "semantic" | "hybrid" | "small_talk" | "unsupported";

type AskResponse = {
  query: string;
  route: Route;
  has_answer: boolean;
  facts: { claim: string; data: Record<string, unknown>; source: string; source_id: string | null }[];
  snippets: {
    content: string;
    document_title: string;
    section_title: string | null;
  }[];
  warnings: string[];
  answer: string | null;
  generation_available: boolean;
};

export type ChatMessage = {
  id: number;
  role: "user" | "ai";
  text: string;
  route?: Route;
  generationUnavailable?: boolean;
};

const ROUTE_LABEL: Record<Route, string> = {
  structured: "structured · live DB",
  semantic: "semantic · documents",
  hybrid: "hybrid · faculty + schedule",
  small_talk: "small talk",
  unsupported: "unsupported",
};

const NO_ANSWER_HINT =
  "I can help with things like your next class, timetable for a specific day, attendance/academic regulations, or which faculty work on a topic — try one of those.";

// Used when generation isn't configured (no Gemini key yet) or produced
// nothing — renders the real, cited retrieval result as text instead of
// failing silently.
function formatFallback(ctx: AskResponse): string {
  if (!ctx.has_answer) {
    if (ctx.route === "unsupported") {
      return `I'm not sure how to help with that yet. ${NO_ANSWER_HINT}`;
    }
    const reason = ctx.warnings[0];
    return reason
      ? `I don't have grounded information for that. (${reason})`
      : "I don't have grounded information for that.";
  }
  const lines: string[] = [];
  for (const f of ctx.facts) lines.push(`• ${f.claim}`);
  for (const s of ctx.snippets) {
    const cite = s.section_title ? `${s.document_title} — ${s.section_title}` : s.document_title;
    const excerpt = s.content.length > 280 ? `${s.content.slice(0, 280).trim()}…` : s.content.trim();
    lines.push(`• [${cite}] ${excerpt}`);
  }
  if (ctx.warnings.length) lines.push("", ...ctx.warnings.map((w) => `⚠️ ${w}`));
  return lines.join("\n");
}

export function ChatBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn("flex gap-2", isUser && "flex-row-reverse")}
    >
      <span
        className={cn(
          "grid size-8 shrink-0 place-items-center rounded-lg",
          isUser ? "bg-secondary text-secondary-foreground" : "bg-primary text-primary-foreground",
        )}
      >
        {isUser ? <span className="text-xs font-bold">ME</span> : <Bot className="size-4" />}
      </span>
      <div className={cn("max-w-[80%] space-y-1.5", isUser && "flex flex-col items-end")}>
        {!isUser && (msg.route || msg.generationUnavailable) ? (
          <div className="flex flex-wrap items-center gap-1.5">
            {msg.route ? (
              <span className="rounded-full border border-border bg-muted px-2 py-0.5 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                {ROUTE_LABEL[msg.route]}
              </span>
            ) : null}
            {msg.generationUnavailable ? (
              <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-600 dark:text-amber-400">
                AI generation not configured
              </span>
            ) : null}
          </div>
        ) : null}
        <div
          className={cn(
            "rounded-xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-line",
            isUser
              ? "rounded-tr-sm bg-secondary text-secondary-foreground"
              : "rounded-tl-sm border border-border bg-card",
          )}
        >
          {msg.text}
        </div>
      </div>
    </motion.div>
  );
}

export function TypingIndicator() {
  return (
    <div className="flex items-center gap-2 text-muted-foreground">
      <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">
        <Bot className="size-4" />
      </span>
      <div className="flex gap-1 rounded-xl border border-border bg-card px-3 py-3">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="size-1.5 animate-bounce pixelated bg-primary"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </div>
    </div>
  );
}

export function AiChatPanel({ compact = false }: { compact?: boolean }) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 1,
      role: "ai",
      text: "Hi! I'm ORION. Ask me about your next class, attendance regulations, or which faculty work on a topic.",
    },
  ]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);

  async function send(text: string) {
    if (!text.trim()) return;
    const id = Date.now();
    setMessages((m) => [...m, { id, role: "user", text }]);
    setInput("");
    setTyping(true);
    try {
      const res = await apiPost<AskResponse>("/ai/ask", { query: text });
      setMessages((m) => [
        ...m,
        {
          id: id + 1,
          role: "ai",
          text: res.answer ?? formatFallback(res),
          route: res.route,
          generationUnavailable: !res.generation_available,
        },
      ]);
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "Sorry, something went wrong reaching ORION's backend.";
      setMessages((m) => [...m, { id: id + 1, role: "ai", text: message }]);
    } finally {
      setTyping(false);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className={cn("scrollbar-thin flex-1 space-y-4 overflow-y-auto p-4", compact && "p-3")}>
        {messages.map((m) => (
          <ChatBubble key={m.id} msg={m} />
        ))}
        {typing ? <TypingIndicator /> : null}
        {messages.length === 1 ? (
          <div className="flex flex-wrap gap-2 pt-2">
            {aiSuggestions.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                className="rounded-lg border border-border bg-card px-3 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
              >
                {s}
              </button>
            ))}
          </div>
        ) : null}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="border-t border-border p-3"
      >
        <div className="flex items-center gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask ORION anything…"
            className="h-10"
            aria-label="Message ORION"
          />
          <Button type="submit" size="icon" className="size-10 shrink-0" aria-label="Send">
            <Send className="size-4" />
          </Button>
        </div>
        <div className="mt-2 flex items-center gap-1 text-muted-foreground">
          <Button type="button" variant="ghost" size="icon" className="size-8" aria-label="Voice input">
            <Mic className="size-4" />
          </Button>
          <Button type="button" variant="ghost" size="icon" className="size-8" aria-label="Upload image">
            <ImagePlus className="size-4" />
          </Button>
          <Button type="button" variant="ghost" size="icon" className="size-8" aria-label="Upload PDF">
            <FileUp className="size-4" />
          </Button>
          <PixelBadge tone="muted" className="ml-auto">
            <Sparkles className="size-3" /> ORION v2
          </PixelBadge>
        </div>
      </form>
    </div>
  );
}

export function FloatingAiButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <AnimatePresence>
        {open ? (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.97 }}
            className="fixed right-3 bottom-24 z-50 flex h-[70vh] w-[min(24rem,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-[var(--shadow-lift)] md:bottom-24"
          >
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <div className="flex items-center gap-2">
                <PixelSprite size={3} rows={[...SPRITES.mascot]} />
                <div>
                  <p className="text-sm font-semibold">ORION Assistant</p>
                  <p className="text-[11px] text-muted-foreground">Always on campus</p>
                </div>
              </div>
              <Button variant="ghost" size="icon" className="size-8" onClick={() => setOpen(false)} aria-label="Close assistant">
                <X className="size-4" />
              </Button>
            </div>
            <AiChatPanel compact />
          </motion.div>
        ) : null}
      </AnimatePresence>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Open ORION assistant"
        className="fixed right-4 bottom-20 z-50 grid size-14 place-items-center rounded-2xl gradient-campus text-primary-foreground shadow-[var(--shadow-lift)] transition-transform hover:scale-105 active:scale-95 md:bottom-6"
      >
        <Sparkles className="size-6" />
      </button>
    </>
  );
}
