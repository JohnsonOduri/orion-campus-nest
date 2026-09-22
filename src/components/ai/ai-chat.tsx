import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { motion } from "framer-motion";
import {
  ArrowDown,
  ArrowUp,
  BookOpen,
  CalendarClock,
  Check,
  Copy,
  Loader2,
  Mic,
  Pause,
  Play,
  RotateCcw,
  Sparkles,
  Square,
  Users,
  UtensilsCrossed,
  Volume2,
  type LucideIcon,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { apiGet, apiPost, ApiError } from "@/lib/api-client";
import { voiceInputService, type VoiceInputError } from "@/lib/ai/voice-input";
import { ttsService, type PlaybackState } from "@/lib/ai/tts";
import { MessageMarkdown } from "./message-markdown";
import { ThinkingOrb } from "./thinking-orb";
import { VoiceMode, type VoiceModeState } from "./voice-mode";

// One example per implemented backend route (docs/query-router.md).
const SUGGESTIONS: { text: string; icon: LucideIcon }[] = [
  { text: "What is my next class?", icon: CalendarClock },
  { text: "What's for lunch today?", icon: UtensilsCrossed },
  { text: "What are the attendance requirements?", icon: BookOpen },
  { text: "Which faculty work in NLP and when can I meet them?", icon: Users },
];

type Route = "structured" | "semantic" | "hybrid" | "small_talk" | "unsupported";

type AskResponse = {
  query: string;
  route: Route;
  has_answer: boolean;
  facts: {
    claim: string;
    data: Record<string, unknown>;
    source: string;
    source_id: string | null;
  }[];
  snippets: { content: string; document_title: string; section_title: string | null }[];
  warnings: string[];
  answer: string | null;
  generation_available: boolean;
  conversation_id: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "ai";
  text: string;
  route?: Route;
  /** Only for a reply that just arrived — drives the typewriter reveal. */
  fresh?: boolean;
  /** Set on a failed request: the user message to resend on Retry. */
  retryOf?: string;
};

const ROUTE_LABEL: Partial<Record<Route, string>> = {
  structured: "Live campus data",
  semantic: "Campus documents",
  hybrid: "Faculty + schedule",
};

const VOICE_ERROR_MESSAGES: Record<VoiceInputError, string> = {
  "no-speech": "I didn't catch that. Tap the orb to try again.",
  "not-allowed":
    "Microphone access is blocked. Allow it in your browser settings to talk to ORION.",
  network: "Voice recognition needs an internet connection.",
  aborted: "",
  unsupported: "Voice input isn't supported in this browser.",
  unknown: "Voice input failed. Please try again.",
};

const NO_ANSWER_HINT =
  "I can help with your next class, the timetable for a day, the mess menu, academic regulations, or which faculty work on a topic.";

// Used when generation isn't configured or produced nothing: shows the real,
// cited retrieval result instead of failing silently.
function formatFallback(ctx: AskResponse): string {
  if (!ctx.has_answer) {
    if (ctx.route === "unsupported")
      return `I'm not sure how to help with that yet. ${NO_ANSWER_HINT}`;
    const reason = ctx.warnings[0];
    return reason
      ? `I don't have grounded information for that. (${reason})`
      : "I don't have grounded information for that.";
  }
  const lines: string[] = [];
  for (const f of ctx.facts) lines.push(`- ${f.claim}`);
  for (const s of ctx.snippets) {
    const cite = s.section_title ? `${s.document_title} — ${s.section_title}` : s.document_title;
    const excerpt =
      s.content.length > 280 ? `${s.content.slice(0, 280).trim()}…` : s.content.trim();
    lines.push(`- [${cite}] ${excerpt}`);
  }
  if (ctx.warnings.length) lines.push("", ...ctx.warnings.map((w) => `⚠️ ${w}`));
  return lines.join("\n");
}

// No backend streaming (single JSON response) — reveal the finished answer
// progressively so it still feels live. Runs once per message.
function useTypewriter(fullText: string, enabled: boolean): string {
  const [shown, setShown] = useState(enabled ? "" : fullText);
  useEffect(() => {
    if (!enabled) {
      setShown(fullText);
      return;
    }
    const words = fullText.split(/(\s+)/);
    let i = 0;
    const id = setInterval(() => {
      i += 3;
      setShown(words.slice(0, i).join(""));
      if (i >= words.length) clearInterval(id);
    }, 30);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return shown;
}

let fallbackNotified = false;

function IconButton({
  label,
  onClick,
  children,
  pressed,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
  pressed?: boolean;
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className="size-9 rounded-full text-muted-foreground hover:text-foreground"
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      onClick={onClick}
    >
      {children}
    </Button>
  );
}

function MessageActions({
  msg,
  playback,
  onSpeak,
  onPause,
  onResume,
  onStop,
  onRegenerate,
}: {
  msg: ChatMessage;
  playback: PlaybackState;
  onSpeak: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onRegenerate: () => void;
}) {
  const [copied, setCopied] = useState(false);

  return (
    <div className="-ml-2 flex items-center transition-opacity md:opacity-70 md:group-hover:opacity-100 md:focus-within:opacity-100">
      {playback === "loading" ? (
        <IconButton label="Preparing audio — tap to cancel" onClick={onStop}>
          <Loader2 className="size-4 animate-spin" />
        </IconButton>
      ) : playback === "speaking" ? (
        <IconButton label="Pause" onClick={onPause} pressed>
          <Pause className="size-4" />
        </IconButton>
      ) : playback === "paused" ? (
        <IconButton label="Resume" onClick={onResume}>
          <Play className="size-4" />
        </IconButton>
      ) : (
        <IconButton label="Read aloud" onClick={onSpeak}>
          <Volume2 className="size-4" />
        </IconButton>
      )}
      {playback !== "idle" ? (
        <IconButton label="Stop" onClick={onStop}>
          <Square className="size-3.5" />
        </IconButton>
      ) : null}
      <IconButton
        label={copied ? "Copied" : "Copy"}
        onClick={() => {
          void navigator.clipboard.writeText(msg.text).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          });
        }}
      >
        {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
      </IconButton>
      <IconButton label="Regenerate" onClick={onRegenerate}>
        <RotateCcw className="size-4" />
      </IconButton>
    </div>
  );
}

function AssistantMessage({ msg, children }: { msg: ChatMessage; children?: React.ReactNode }) {
  const shown = useTypewriter(msg.text, !!msg.fresh);
  const label = msg.route ? ROUTE_LABEL[msg.route] : undefined;
  const isError = !!msg.retryOf;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="group flex flex-col gap-1.5"
    >
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="grid size-6 place-items-center rounded-full bg-primary/10 text-primary">
          <Sparkles className="size-3.5" />
        </span>
        <span className="font-medium text-foreground">ORION</span>
        {label ? <span>· {label}</span> : null}
      </div>
      <div className={cn("pl-8", isError && "text-destructive")}>
        <MessageMarkdown content={shown} className="text-[15px] leading-7" />
      </div>
      <div className="pl-8">{children}</div>
    </motion.div>
  );
}

function UserMessage({ msg }: { msg: ChatMessage }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="flex justify-end"
    >
      <div className="max-w-[85%] rounded-3xl rounded-br-lg bg-secondary px-4 py-2.5 text-[15px] leading-relaxed break-words whitespace-pre-wrap text-secondary-foreground">
        {msg.text}
      </div>
    </motion.div>
  );
}

function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="flex min-h-full flex-col items-center justify-center px-2 py-10 text-center">
      <ThinkingOrb state="idle" size={64} showLabel={false} />
      <h2 className="mt-5 text-xl font-semibold tracking-tight">How can I help?</h2>
      <p className="mt-1.5 max-w-sm text-sm text-muted-foreground">
        Ask about your classes, faculty, the mess menu or campus rules — type, or tap the mic and
        talk.
      </p>
      <div className="mt-7 grid w-full max-w-lg gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map(({ text, icon: Icon }) => (
          <button
            key={text}
            type="button"
            onClick={() => onPick(text)}
            className="flex min-h-12 items-center gap-3 rounded-2xl border border-border bg-card px-4 py-3 text-left text-sm transition-colors hover:border-primary/40 hover:bg-muted focus-visible:outline-2 focus-visible:outline-primary"
          >
            <Icon className="size-4 shrink-0 text-primary" />
            <span>{text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function Composer({
  value,
  onChange,
  onSubmit,
  onMic,
  busy,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onMic: () => void;
  busy: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    // Desktop: Enter sends, Shift+Enter is a newline. Touch keyboards: Enter
    // is a newline and the send button sends (like other chat apps).
    if (e.key !== "Enter" || e.shiftKey || e.nativeEvent.isComposing) return;
    if (window.matchMedia("(pointer: coarse)").matches) return;
    e.preventDefault();
    onSubmit();
  }

  const canSend = value.trim().length > 0 && !busy;

  return (
    <form
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        onSubmit();
      }}
      className="mx-auto flex w-full max-w-3xl items-end gap-1.5 rounded-[1.75rem] border border-border bg-card p-1.5 pl-4 shadow-sm transition-shadow focus-within:border-primary/40 focus-within:shadow-md"
    >
      <textarea
        ref={ref}
        rows={1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Message ORION"
        aria-label="Message ORION"
        enterKeyHint="send"
        className="max-h-40 min-h-11 flex-1 resize-none bg-transparent py-2.5 text-base leading-6 outline-none placeholder:text-muted-foreground md:text-[15px]"
      />
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={onMic}
        aria-label="Talk to ORION"
        title="Talk to ORION"
        className="size-11 shrink-0 rounded-full"
      >
        <Mic className="size-5" />
      </Button>
      <Button
        type="submit"
        size="icon"
        disabled={!canSend}
        aria-label="Send message"
        className="size-11 shrink-0 rounded-full"
      >
        <ArrowUp className="size-5" />
      </Button>
    </form>
  );
}

export function AiChatPanel({
  initialConversationId = null,
  initialQuestion,
  onInitialQuestionSent,
  onConversationCreated,
}: {
  initialConversationId?: string | null;
  initialQuestion?: string;
  onInitialQuestionSent?: () => void;
  onConversationCreated?: (id: string) => void;
}) {
  const [conversationId, setConversationId] = useState<string | null>(initialConversationId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(!!initialConversationId);
  const [input, setInput] = useState("");
  const [processing, setProcessing] = useState(false);

  // Which message the speaker controls belong to ("voice" = voice-mode answer).
  const [speechTarget, setSpeechTarget] = useState<string | null>(null);
  const [playback, setPlayback] = useState<PlaybackState>("idle");

  const [voiceModeOpen, setVoiceModeOpen] = useState(false);
  const [voiceState, setVoiceState] = useState<VoiceModeState>("ready");
  const [voiceTranscript, setVoiceTranscript] = useState("");
  const [voiceResponse, setVoiceResponse] = useState<string | null>(null);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  // Every listen starts a new voice turn; an answer only speaks if its turn
  // is still current (the user hasn't interrupted or closed voice mode).
  const voiceTurnRef = useRef(0);
  const voiceOpenRef = useRef(false);
  const errorTimerRef = useRef<number | undefined>(undefined);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const [atBottom, setAtBottom] = useState(true);

  useEffect(() => {
    if (!initialConversationId) return;
    let cancelled = false;
    setLoadingHistory(true);
    apiGet<{
      conversation_id: string;
      messages: { id: string; role: string; content: string; route: string | null }[];
    }>(`/ai/conversations/${initialConversationId}/messages`)
      .then((res) => {
        if (cancelled) return;
        setMessages(
          res.messages.map((m) => ({
            id: m.id,
            role: m.role === "user" ? "user" : "ai",
            text: m.content,
            route: (m.route as Route) ?? undefined,
          })),
        );
      })
      .catch(() => {
        if (!cancelled) toast.error("Couldn't load that conversation.");
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false);
      });
    return () => {
      cancelled = true;
    };
  }, [initialConversationId]);

  const askedRef = useRef(false);
  useEffect(() => {
    if (!initialQuestion || askedRef.current || initialConversationId) return;
    askedRef.current = true;
    void send(initialQuestion);
    onInitialQuestionSent?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuestion]);

  // Follow new content (including the typewriter reveal) only while the user
  // is already at the bottom — never yank them away from older messages.
  useEffect(() => {
    const scroller = scrollRef.current;
    const content = contentRef.current;
    if (!scroller || !content) return;
    const observer = new ResizeObserver(() => {
      if (stickToBottomRef.current) scroller.scrollTop = scroller.scrollHeight;
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const offState = ttsService.onStateChange((s) => {
      setPlayback(s);
      if (s === "idle") setSpeechTarget(null);
    });
    const offFallback = ttsService.onFallback(() => {
      if (fallbackNotified) return;
      fallbackNotified = true;
      toast.message("Using your device's voice", {
        description: "ORION's neural voice isn't reachable right now.",
      });
    });
    return () => {
      offState();
      offFallback();
      abortRef.current?.abort();
      ttsService.stop();
      voiceInputService.cancel();
      window.clearTimeout(errorTimerRef.current);
    };
  }, []);

  function handleScroll() {
    const el = scrollRef.current;
    if (!el) return;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    stickToBottomRef.current = near;
    setAtBottom(near);
  }

  function scrollToBottom() {
    const el = scrollRef.current;
    if (!el) return;
    stickToBottomRef.current = true;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }

  async function send(text: string, opts?: { voiceTurn?: number }) {
    const trimmed = text.trim();
    if (!trimmed) return;

    // A new question always silences the previous answer.
    ttsService.stop();
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const userId = crypto.randomUUID();
    setMessages((m) => [...m, { id: userId, role: "user", text: trimmed }]);
    setInput("");
    setProcessing(true);
    stickToBottomRef.current = true;
    const voiceTurn = opts?.voiceTurn;
    if (voiceTurn !== undefined) setVoiceState("processing");

    let answerText: string;
    try {
      const res = await apiPost<AskResponse>(
        "/ai/ask",
        { query: trimmed, conversation_id: conversationId },
        { signal: controller.signal },
      );
      if (!conversationId) {
        setConversationId(res.conversation_id);
        onConversationCreated?.(res.conversation_id);
      }
      answerText = res.answer ?? formatFallback(res);
      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          role: "ai",
          text: answerText,
          route: res.route,
          fresh: true,
        },
      ]);
    } catch (error) {
      if (controller.signal.aborted) return;
      const message =
        error instanceof ApiError
          ? error.message
          : "I couldn't reach ORION's server. Check your connection and try again.";
      setMessages((m) => [
        ...m,
        { id: crypto.randomUUID(), role: "ai", text: message, retryOf: userId },
      ]);
      if (voiceTurn !== undefined && voiceTurn === voiceTurnRef.current) {
        setVoiceState("error");
        setVoiceError(message);
      }
      return;
    } finally {
      if (abortRef.current === controller) setProcessing(false);
    }

    if (voiceTurn === undefined || voiceTurn !== voiceTurnRef.current || !voiceOpenRef.current)
      return;

    setVoiceResponse(answerText);
    setSpeechTarget("voice");
    const result = await ttsService.speak(answerText, {
      onStart: () => {
        if (voiceTurn === voiceTurnRef.current) setVoiceState("responding");
      },
    });
    if (voiceTurn !== voiceTurnRef.current) return; // interrupted by a new turn / close
    if (result === "failed") {
      setVoiceState("error");
      setVoiceError("I couldn't play the spoken reply — the answer is shown below.");
      window.clearTimeout(errorTimerRef.current);
      errorTimerRef.current = window.setTimeout(() => {
        setVoiceState((s) => (s === "error" ? "ready" : s));
      }, 4000);
    } else {
      setVoiceState((s) => (s === "responding" || s === "processing" ? "ready" : s));
    }
  }

  function submitTyped(text: string) {
    ttsService.unlock(); // inside the tap/keypress: lets later audio play on mobile
    void send(text);
  }

  function regenerate(fromIndex: number) {
    const priorUser = [...messages.slice(0, fromIndex)].reverse().find((m) => m.role === "user");
    if (priorUser) submitTyped(priorUser.text);
  }

  function retry(errorMsg: ChatMessage) {
    const original = messages.find((m) => m.id === errorMsg.retryOf);
    if (!original) return;
    setMessages((m) => m.filter((x) => x.id !== errorMsg.id && x.id !== original.id));
    submitTyped(original.text);
  }

  function speakMessage(msg: ChatMessage) {
    ttsService.unlock();
    ttsService.stop();
    setSpeechTarget(msg.id);
    void ttsService.speak(msg.text).then((result) => {
      if (result === "failed") toast.error("Couldn't play audio for that answer.");
    });
  }

  function startListening() {
    ttsService.stop(); // barge-in: never listen while ORION is talking
    window.clearTimeout(errorTimerRef.current);
    const turn = ++voiceTurnRef.current;
    setVoiceTranscript("");
    setVoiceError(null);
    setVoiceResponse(null);
    setVoiceState("listening");
    voiceInputService.start({
      onTranscript: (t, isFinal) => {
        if (turn !== voiceTurnRef.current) return;
        setVoiceTranscript(t);
        if (isFinal) void send(t, { voiceTurn: turn });
      },
      onError: (err) => {
        if (err === "aborted" || turn !== voiceTurnRef.current) return;
        setVoiceState("error");
        setVoiceError(VOICE_ERROR_MESSAGES[err]);
      },
      onEnd: () => {
        if (turn !== voiceTurnRef.current) return;
        setVoiceState((s) => (s === "listening" ? "ready" : s));
      },
    });
  }

  function openVoiceMode() {
    ttsService.unlock();
    if (!voiceInputService.supported()) {
      toast.error("Voice input isn't supported in this browser.", {
        description: "Try Chrome or Safari. You can still type your question.",
      });
      return;
    }
    voiceOpenRef.current = true;
    setVoiceModeOpen(true);
    startListening();
  }

  function closeVoiceMode() {
    voiceInputService.cancel();
    ttsService.stop();
    voiceTurnRef.current++;
    voiceOpenRef.current = false;
    window.clearTimeout(errorTimerRef.current);
    setVoiceModeOpen(false);
    setVoiceState("ready");
    setVoiceTranscript("");
  }

  function handleOrbTap() {
    ttsService.unlock();
    if (voiceState === "listening") {
      voiceInputService.stop(); // finalises whatever was heard
    } else {
      startListening(); // from speaking/thinking this is a barge-in
    }
  }

  function stopVoiceSpeaking() {
    voiceTurnRef.current++;
    ttsService.stop();
    setVoiceState("ready");
  }

  const empty = !loadingHistory && messages.length === 0;

  return (
    <div className="relative flex h-full min-h-0 flex-col">
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="scrollbar-thin min-h-0 flex-1 overflow-y-auto"
      >
        <div
          ref={contentRef}
          className={cn("mx-auto w-full max-w-3xl px-4 py-6", empty && "h-full")}
        >
          {loadingHistory ? (
            <div className="flex justify-center py-10">
              <ThinkingOrb state="processing" size={32} showLabel={false} />
            </div>
          ) : empty ? (
            <EmptyState onPick={submitTyped} />
          ) : (
            <div className="space-y-6">
              {messages.map((m, i) =>
                m.role === "user" ? (
                  <UserMessage key={m.id} msg={m} />
                ) : (
                  <AssistantMessage key={m.id} msg={m}>
                    {m.retryOf ? (
                      <Button
                        variant="outline"
                        size="sm"
                        className="mt-1 h-9 gap-1.5 rounded-full"
                        onClick={() => retry(m)}
                      >
                        <RotateCcw className="size-3.5" /> Retry
                      </Button>
                    ) : (
                      <MessageActions
                        msg={m}
                        playback={speechTarget === m.id ? playback : "idle"}
                        onSpeak={() => speakMessage(m)}
                        onPause={ttsService.pause}
                        onResume={ttsService.resume}
                        onStop={ttsService.stop}
                        onRegenerate={() => regenerate(i)}
                      />
                    )}
                  </AssistantMessage>
                ),
              )}
              {processing ? (
                <div className="flex items-center gap-3" role="status">
                  <ThinkingOrb state="processing" size={32} showLabel={false} />
                  <span className="text-sm text-muted-foreground">Thinking…</span>
                </div>
              ) : null}
            </div>
          )}
        </div>
      </div>

      <div className="relative border-t border-border/60 bg-background/85 px-3 pt-2.5 pb-3 backdrop-blur-md md:pb-[calc(0.75rem+env(safe-area-inset-bottom))]">
        {!atBottom && !empty ? (
          <button
            type="button"
            onClick={scrollToBottom}
            aria-label="Scroll to latest message"
            className="absolute -top-14 left-1/2 grid size-10 -translate-x-1/2 place-items-center rounded-full border border-border bg-card shadow-md transition-colors hover:bg-muted"
          >
            <ArrowDown className="size-4" />
          </button>
        ) : null}
        <Composer
          value={input}
          onChange={setInput}
          onSubmit={() => submitTyped(input)}
          onMic={openVoiceMode}
          busy={processing}
        />
        <p className="mt-2 hidden text-center text-[11px] text-muted-foreground sm:block">
          ORION answers from campus data and can still make mistakes.
        </p>
      </div>

      <VoiceMode
        open={voiceModeOpen}
        state={voiceState}
        transcript={voiceTranscript}
        response={voiceResponse}
        errorMessage={voiceError}
        onOrbTap={handleOrbTap}
        onStopSpeaking={stopVoiceSpeaking}
        onClose={closeVoiceMode}
      />
    </div>
  );
}
