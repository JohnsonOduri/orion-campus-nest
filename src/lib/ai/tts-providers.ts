import { apiPostBlob } from "@/lib/api-client";
import { audioElement } from "./audio-output";

// Provider contract. The UI never touches these directly — it calls
// ttsService (./tts.ts), which picks a provider and sequences playback.
export interface TTSOptions {
  voice?: string; // Kokoro voice id, e.g. "af_heart"; ignored by the browser provider
  speed?: number; // 1 = normal
}

/** Something that can be played once. Created by a provider, owned by the AudioManager. */
export interface AudioSource {
  readonly provider: TTSProviderId;
  /** Resolves when playback ends or is stopped; rejects if it could not play. */
  play(): Promise<void>;
  pause(): void;
  resume(): void;
  stop(): void;
  /** Releases resources (object URLs). Safe to call more than once. */
  dispose(): void;
}

export type TTSProviderId = "browser" | "kokoro";

export interface TTSProvider {
  readonly id: TTSProviderId;
  synthesize(text: string, options?: TTSOptions, signal?: AbortSignal): Promise<AudioSource>;
  stop(): void;
}

// --- Browser SpeechSynthesis -------------------------------------------------

class UtteranceSource implements AudioSource {
  readonly provider = "browser" as const;
  private settle: (() => void) | null = null;

  constructor(
    private readonly text: string,
    private readonly options: TTSOptions,
  ) {}

  play(): Promise<void> {
    const synth = window.speechSynthesis;
    return new Promise((resolve, reject) => {
      const utter = new SpeechSynthesisUtterance(this.text);
      utter.lang = "en-US";
      utter.rate = this.options.speed ?? 1;
      this.settle = resolve;
      utter.onend = () => resolve();
      utter.onerror = (e) => {
        // "interrupted"/"canceled" come from stop() or a newer request — not failures.
        if (e.error === "interrupted" || e.error === "canceled") resolve();
        else reject(new Error(`speech synthesis failed: ${e.error}`));
      };
      synth.speak(utter);
    });
  }

  pause(): void {
    window.speechSynthesis.pause();
  }

  resume(): void {
    window.speechSynthesis.resume();
  }

  stop(): void {
    window.speechSynthesis.cancel();
    this.settle?.();
  }

  dispose(): void {
    this.settle = null;
  }
}

export class BrowserTTSProvider implements TTSProvider {
  readonly id = "browser" as const;

  supported(): boolean {
    return typeof window !== "undefined" && "speechSynthesis" in window;
  }

  // SpeechSynthesis renders at play time, so "synthesis" is just packaging.
  async synthesize(text: string, options: TTSOptions = {}): Promise<AudioSource> {
    if (!this.supported()) throw new Error("Speech synthesis not supported in this browser");
    return new UtteranceSource(text, options);
  }

  stop(): void {
    if (this.supported()) window.speechSynthesis.cancel();
  }
}

// --- Kokoro (through ORION's /tts/speech proxy) ----------------------------------

class ElementSource implements AudioSource {
  readonly provider = "kokoro" as const;
  private url: string | null = null;
  private settle: (() => void) | null = null;

  constructor(private readonly blob: Blob) {}

  play(): Promise<void> {
    const el = audioElement();
    this.url = URL.createObjectURL(this.blob);
    el.src = this.url;
    return new Promise((resolve, reject) => {
      const cleanup = () => {
        el.onended = null;
        el.onerror = null;
        this.settle = null;
      };
      this.settle = () => {
        cleanup();
        resolve();
      };
      el.onended = () => {
        cleanup();
        resolve();
      };
      el.onerror = () => {
        cleanup();
        reject(new Error("audio playback failed"));
      };
      // NotAllowedError here means the browser blocked playback (no prior gesture).
      el.play().catch((err: unknown) => {
        cleanup();
        reject(err instanceof Error ? err : new Error("audio playback blocked"));
      });
    });
  }

  pause(): void {
    audioElement().pause();
  }

  resume(): void {
    void audioElement().play();
  }

  stop(): void {
    const el = audioElement();
    el.pause();
    this.settle?.();
  }

  dispose(): void {
    if (this.url) {
      URL.revokeObjectURL(this.url);
      this.url = null;
    }
  }
}

const CACHE_LIMIT = 40;

export class KokoroTTSProvider implements TTSProvider {
  readonly id = "kokoro" as const;
  // Replaying an answer (speaker button) reuses its audio instead of
  // re-synthesising. Memory only, small, dropped on reload.
  private cache = new Map<string, Blob>();

  async synthesize(
    text: string,
    options: TTSOptions = {},
    signal?: AbortSignal,
  ): Promise<AudioSource> {
    const key = `${options.voice ?? ""}|${options.speed ?? ""}|${text}`;
    const cached = this.cache.get(key);
    if (cached) {
      this.cache.delete(key);
      this.cache.set(key, cached);
      return new ElementSource(cached);
    }

    // A hung server must not leave the orb "thinking" forever.
    const timeout = AbortSignal.timeout(20_000);
    const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;
    const blob = await apiPostBlob(
      "/tts/speech",
      { text, voice: options.voice, speed: options.speed },
      { signal: combined },
    );
    if (!blob.type.startsWith("audio/")) throw new Error("voice service did not return audio");

    this.cache.set(key, blob);
    if (this.cache.size > CACHE_LIMIT) {
      const oldest = this.cache.keys().next().value;
      if (oldest !== undefined) this.cache.delete(oldest);
    }
    return new ElementSource(blob);
  }

  stop(): void {
    audioElement().pause();
  }
}
