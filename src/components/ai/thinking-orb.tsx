import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ThinkingOrb as Orb, type OrbState } from "thinking-orbs";
import { MODE_FRAMES, paintFrame, resolvePreset } from "thinking-orbs/engine";
import { cn } from "@/lib/utils";

// Adapts github.com/Jakubantalik/thinking-orbs (MIT) to ORION's chat states.
// This file is the only place ORION's states map to the library's — and the
// orb is only used inside src/components/ai/.
export type ChatOrbState = "idle" | "listening" | "processing" | "responding" | "error";

const STATE_MAP: Record<ChatOrbState, { orb: OrbState; label: string }> = {
  idle: { orb: "breathing", label: "" },
  listening: { orb: "listening", label: "Listening…" },
  processing: { orb: "searching", label: "Thinking…" },
  responding: { orb: "composing", label: "Speaking…" },
  error: { orb: "breathing", label: "Something went wrong" },
};

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);
  return reduced;
}

function useDarkTheme(): boolean {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const root = document.documentElement;
    const read = () => setDark(root.classList.contains("dark"));
    read();
    const observer = new MutationObserver(read);
    observer.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);
  return dark;
}

/**
 * The library's canvas is sized for 64/32/20 px only; CSS-scaling it up blurs
 * on phones. For the voice screen we paint the tuned 64 px design (same dots,
 * same proportions) through a scaled transform, so it stays sharp at any size.
 */
function LargeOrb({ state, size, speed = 1 }: { state: OrbState; size: number; speed?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const dark = useDarkTheme();
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const dpr = Math.min(3, window.devicePixelRatio || 1);
    canvas.width = Math.round(size * dpr);
    canvas.height = Math.round(size * dpr);
    const { mode, speed: baseSpeed, opts } = resolvePreset(state, 64);
    const frameFn = MODE_FRAMES[mode];
    const scale = (size / 64) * dpr;
    const draw = (t: number) => {
      ctx.setTransform(scale, 0, 0, scale, 0, 0);
      ctx.clearRect(0, 0, 64, 64);
      paintFrame(ctx, frameFn(64, t, opts), dark);
    };

    if (reduced) {
      draw(0.6);
      return;
    }
    let raf = 0;
    const loop = () => {
      draw((performance.now() / 1000) * baseSpeed * speed);
      raf = requestAnimationFrame(loop);
    };
    const onVisibility = () => {
      cancelAnimationFrame(raf);
      if (document.visibilityState === "visible") raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [state, size, speed, dark, reduced]);

  return <canvas ref={ref} aria-hidden style={{ width: size, height: size, display: "block" }} />;
}

export function ThinkingOrb({
  state,
  size = 64,
  showLabel = true,
  className,
}: {
  state: ChatOrbState;
  /** 20 / 32 / 64 use the library's tuned presets; anything larger renders the 64 design scaled. */
  size?: number;
  showLabel?: boolean;
  className?: string;
}) {
  const { orb, label } = STATE_MAP[state];
  const large = size > 64;
  const presetSize = size <= 20 ? 20 : size <= 32 ? 32 : 64;

  return (
    <div className={cn("flex flex-col items-center gap-2", className)}>
      <div
        role="img"
        aria-label={label || "ORION assistant"}
        className="relative"
        style={{ width: size, height: size }}
      >
        {/* Crossfade between states instead of snapping from one animation to the next. */}
        <AnimatePresence initial={false}>
          <motion.div
            key={orb}
            className="absolute inset-0"
            initial={{ opacity: 0, scale: 0.94 }}
            animate={{ opacity: state === "error" ? 0.45 : 1, scale: 1 }}
            exit={{ opacity: 0, scale: 1.04 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
          >
            {large ? (
              <LargeOrb state={orb} size={size} speed={state === "error" ? 0.3 : 1} />
            ) : (
              <Orb state={orb} size={presetSize} theme="auto" aria-hidden />
            )}
          </motion.div>
        </AnimatePresence>
      </div>
      {showLabel && label ? (
        <p className="text-xs font-medium text-muted-foreground" aria-live="polite">
          {label}
        </p>
      ) : null}
    </div>
  );
}
