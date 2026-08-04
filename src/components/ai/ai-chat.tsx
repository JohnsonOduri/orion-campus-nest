import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Bot, Send, Sparkles, Mic, ImagePlus, FileUp, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { PixelBadge, PixelSprite, SPRITES } from "@/components/pixel/pixel-art";
import { aiSuggestions } from "@/lib/mock-data";

export type ChatMessage = { id: number; role: "user" | "ai"; text: string };

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
        {isUser ? <span className="text-xs font-bold">AM</span> : <Bot className="size-4" />}
      </span>
      <div
        className={cn(
          "max-w-[80%] rounded-xl px-3.5 py-2.5 text-sm leading-relaxed",
          isUser
            ? "rounded-tr-sm bg-secondary text-secondary-foreground"
            : "rounded-tl-sm border border-border bg-card",
        )}
      >
        {msg.text}
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

const CANNED =
  "Here's what I found: you have 3 classes left today, CS306 is running now in LH-2, and your ML assignment is due in 2 days. Want me to draft a revision plan?";

export function AiChatPanel({ compact = false }: { compact?: boolean }) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: 1, role: "ai", text: "Hi Aarav! I'm ORION. Ask me anything about classes, mess, faculty or deadlines." },
  ]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);

  function send(text: string) {
    if (!text.trim()) return;
    const id = Date.now();
    setMessages((m) => [...m, { id, role: "user", text }]);
    setInput("");
    setTyping(true);
    setTimeout(() => {
      setTyping(false);
      setMessages((m) => [...m, { id: id + 1, role: "ai", text: CANNED }]);
    }, 1100);
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
