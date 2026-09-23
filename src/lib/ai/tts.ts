import { unlockAudio } from "./audio-output";
import { sanitizeForSpeech, splitIntoSpeechChunks } from "./speech-text";
import {
  BrowserTTSProvider,
  KokoroBrowserProvider,
  KOKORO_DEFAULT_VOICE,
  getKokoroLoadState,
  onKokoroLoadStateChange,
  type AudioSource,
  type KokoroLoadState,
  type TTSOptions,
  type TTSProvider,
  type TTSProviderId,
} from "./tts-providers";

export type PlaybackState = "idle" | "loading" | "speaking" | "paused";
export type SpeakResult = "completed" | "interrupted" | "failed";

export type SpeakOptions = TTSOptions & {
  /** Fires once, when the first audio actually starts — the orb's cue to show "responding". */
  onStart?: (provider: TTSProviderId) => void;
};

type ResolvedPlan = { provider: TTSProviderId; options: TTSOptions };

// After Kokoro fails, don't make every following answer wait for it to fail again.
const KOKORO_RETRY_AFTER_MS = 60_000;

/**
 * Sequences speech for one answer at a time.
 *
 * - Every speak()/interrupt() bumps `requestId`; any async step that finds
 *   its id is no longer current stops and disposes what it holds. That's what
 *   guarantees an old answer can never start (or keep) talking after a newer
 *   one or a barge-in.
 * - While chunk N plays, chunk N+1 is already being synthesised, so there is
 *   no gap between sentences on the network-backed provider.
 * - If Kokoro can't synthesise or play a chunk, that chunk and the rest of
 *   the answer fall back to the browser voice. Only when the browser voice
 *   also fails does speak() report "failed" — the text answer is unaffected.
 */
export class AudioManager {
  private requestId = 0;
  private state: PlaybackState = "idle";
  private current: AudioSource | null = null;
  private controller: AbortController | null = null;
  private kokoroRetryAt = 0;
  private stateListeners = new Set<(s: PlaybackState) => void>();
  private fallbackListeners = new Set<() => void>();

  constructor(
    private readonly browser: TTSProvider,
    private readonly neural: TTSProvider,
    private readonly plan: (opts: TTSOptions) => Promise<ResolvedPlan>,
    private readonly now: () => number = () => Date.now(),
  ) {}

  getState(): PlaybackState {
    return this.state;
  }

  onStateChange(fn: (s: PlaybackState) => void): () => void {
    this.stateListeners.add(fn);
    return () => this.stateListeners.delete(fn);
  }

  /** Fires when the neural voice was wanted but the browser voice had to be used. */
  onFallback(fn: () => void): () => void {
    this.fallbackListeners.add(fn);
    return () => this.fallbackListeners.delete(fn);
  }

  private setState(state: PlaybackState) {
    if (this.state === state) return;
    this.state = state;
    for (const fn of this.stateListeners) fn(state);
  }

  /** Stops current audio and cancels anything queued or still being synthesised. */
  interrupt(): void {
    this.requestId++;
    this.controller?.abort();
    this.controller = null;
    this.current?.stop();
    this.current?.dispose();
    this.current = null;
    this.browser.stop();
    this.neural.stop();
    this.setState("idle");
  }

  pause(): void {
    if (this.state !== "speaking" || !this.current) return;
    this.current.pause();
    this.setState("paused");
  }

  resume(): void {
    if (this.state !== "paused" || !this.current) return;
    this.current.resume();
    this.setState("speaking");
  }

  async speak(markdown: string, opts: SpeakOptions = {}): Promise<SpeakResult> {
    this.interrupt();
    const id = this.requestId;
    const isStale = () => id !== this.requestId;
    const controller = new AbortController();
    this.controller = controller;

    const chunks = splitIntoSpeechChunks(sanitizeForSpeech(markdown));
    if (chunks.length === 0) return "completed";

    this.setState("loading");
    const { provider, options } = await this.plan(opts);
    if (isStale()) return "interrupted";

    let useNeural = provider === "kokoro" && this.now() >= this.kokoroRetryAt;
    const giveUpOnNeural = () => {
      if (!useNeural) return;
      useNeural = false;
      this.kokoroRetryAt = this.now() + KOKORO_RETRY_AFTER_MS;
      for (const fn of this.fallbackListeners) fn();
    };

    const synthesize = async (text: string): Promise<AudioSource> => {
      if (useNeural) {
        try {
          return await this.neural.synthesize(text, options, controller.signal);
        } catch (err) {
          if (controller.signal.aborted) throw err;
          giveUpOnNeural();
        }
      }
      return this.browser.synthesize(text, options, controller.signal);
    };
    const prefetch = (text: string) => {
      const p = synthesize(text);
      p.catch(() => {}); // awaited later; don't report an unhandled rejection meanwhile
      return p;
    };

    let next: Promise<AudioSource> | null = prefetch(chunks[0]!);
    let started = false;

    try {
      for (let i = 0; i < chunks.length; i++) {
        const source: AudioSource = await next!;
        if (isStale()) {
          source.dispose();
          return "interrupted";
        }
        next = i + 1 < chunks.length ? prefetch(chunks[i + 1]!) : null;

        let playing = source;
        this.current = playing;
        if (!started) {
          started = true;
          this.setState("speaking");
          opts.onStart?.(playing.provider);
        }

        try {
          await playing.play();
        } catch (err) {
          playing.dispose();
          if (isStale()) return "interrupted";
          if (playing.provider !== "kokoro") throw err;
          // Kokoro audio arrived but wouldn't play (decode error, or the
          // browser blocked it) — say this chunk with the browser voice.
          giveUpOnNeural();
          playing = await this.browser.synthesize(chunks[i]!, options);
          this.current = playing;
          await playing.play();
        }
        playing.dispose();
        if (isStale()) return "interrupted";
      }
      return "completed";
    } catch (err) {
      if (isStale() || controller.signal.aborted) return "interrupted";
      console.warn("[tts] speech failed:", err instanceof Error ? err.message : err);
      return "failed";
    } finally {
      next?.then(
        (s) => s.dispose(),
        () => {},
      );
      if (!isStale()) {
        this.current = null;
        this.controller = null;
        this.setState("idle");
      }
    }
  }
}

const browserProvider = new BrowserTTSProvider();
const kokoroProvider = new KokoroBrowserProvider();

// RION's voice is fixed, not user-configurable: provider = kokoro (running
// on-device), voice = af_heart, speed = 1. There is no backend to ask
// anymore — the model lives and runs entirely in this browser tab.
const manager = new AudioManager(browserProvider, kokoroProvider, (opts) =>
  Promise.resolve({
    provider: "kokoro",
    options: { voice: opts.voice ?? KOKORO_DEFAULT_VOICE, speed: opts.speed ?? 1 },
  }),
);

/**
 * The only speech API the UI uses. Kokoro runs on-device (primary), with the
 * browser's own voice as the automatic fallback — components never call
 * speechSynthesis directly, and there is no backend TTS endpoint.
 */
export const ttsService = {
  speak: (markdown: string, opts?: SpeakOptions) => manager.speak(markdown, opts),
  stop: () => manager.interrupt(),
  pause: () => manager.pause(),
  resume: () => manager.resume(),
  getState: () => manager.getState(),
  onStateChange: (fn: (s: PlaybackState) => void) => manager.onStateChange(fn),
  onFallback: (fn: () => void) => manager.onFallback(fn),
  /** Call synchronously inside a tap/click, before any await (see audio-output.ts). */
  unlock: unlockAudio,
  /** State of RION's on-device voice model — for a first-use "preparing voice" message only. */
  getVoiceLoadState: getKokoroLoadState,
  onVoiceLoadStateChange: (fn: (s: KokoroLoadState) => void) => onKokoroLoadStateChange(fn),
};
