import { AnimatePresence, motion } from "framer-motion";
import { Mic, Square, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MessageMarkdown } from "./message-markdown";
import { ThinkingOrb, type ChatOrbState } from "./thinking-orb";

// Full-screen voice conversation. The orb is the main control: tap it to
// talk, tap it while ORION is speaking to interrupt and talk again.
export type VoiceModeState = "listening" | "processing" | "responding" | "ready" | "error";

const STATE_TO_ORB: Record<VoiceModeState, ChatOrbState> = {
  listening: "listening",
  processing: "processing",
  responding: "responding",
  ready: "idle",
  error: "error",
};

const STATUS: Record<VoiceModeState, string> = {
  listening: "Listening…",
  processing: "Thinking…",
  responding: "Speaking…",
  ready: "Tap the orb to talk",
  error: "",
};

const ORB_LABEL: Record<VoiceModeState, string> = {
  listening: "Stop listening",
  processing: "Interrupt and talk",
  responding: "Interrupt and talk",
  ready: "Start listening",
  error: "Try again",
};

export function VoiceMode({
  open,
  state,
  transcript,
  response,
  errorMessage,
  onOrbTap,
  onStopSpeaking,
  onClose,
}: {
  open: boolean;
  state: VoiceModeState;
  transcript: string;
  /** ORION's latest answer in this voice session, shown as text too. */
  response: string | null;
  errorMessage?: string | null;
  onOrbTap: () => void;
  onStopSpeaking: () => void;
  onClose: () => void;
}) {
  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
          role="dialog"
          aria-modal="true"
          aria-label="ORION voice conversation"
          className="fixed inset-0 z-[60] flex flex-col bg-background px-5 pt-[calc(env(safe-area-inset-top)+0.75rem)] pb-[calc(env(safe-area-inset-bottom)+1.25rem)]"
        >
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold tracking-wide text-muted-foreground">ORION</span>
            <Button
              variant="ghost"
              size="icon"
              onClick={onClose}
              aria-label="Close voice mode"
              className="size-11 rounded-full"
            >
              <X className="size-5" />
            </Button>
          </div>

          <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-8">
            <motion.button
              type="button"
              onClick={onOrbTap}
              aria-label={ORB_LABEL[state]}
              aria-pressed={state === "listening"}
              whileTap={{ scale: 0.95 }}
              className="rounded-full focus-visible:outline-2 focus-visible:outline-offset-8 focus-visible:outline-primary"
            >
              <ThinkingOrb state={STATE_TO_ORB[state]} size={176} showLabel={false} />
            </motion.button>

            <div className="flex w-full max-w-md flex-col items-center gap-3 text-center">
              {state === "error" ? (
                <p className="text-sm text-destructive" role="alert">
                  {errorMessage ?? "Something went wrong."}
                </p>
              ) : (
                <p className="text-base font-medium" aria-live="polite">
                  {STATUS[state]}
                </p>
              )}
              {transcript && (state === "listening" || state === "processing") ? (
                <p className="text-lg leading-snug text-foreground/80">“{transcript}”</p>
              ) : null}
              {response && (state === "responding" || state === "ready" || state === "error") ? (
                <div className="scrollbar-thin max-h-[30dvh] w-full overflow-y-auto text-left text-muted-foreground">
                  <MessageMarkdown content={response} />
                </div>
              ) : null}
            </div>
          </div>

          <div className="flex h-14 items-center justify-center gap-3">
            {state === "responding" ? (
              <Button
                variant="secondary"
                onClick={onStopSpeaking}
                className="h-11 gap-2 rounded-full px-5"
              >
                <Square className="size-4" /> Stop
              </Button>
            ) : state === "ready" || state === "error" ? (
              <Button onClick={onOrbTap} className="h-11 gap-2 rounded-full px-5">
                <Mic className="size-4" /> {state === "error" ? "Try again" : "Talk"}
              </Button>
            ) : null}
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
