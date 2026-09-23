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

// --- Browser SpeechSynthesis (fallback provider) -----------------------------

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

// --- Kokoro, running 100% locally in the browser (kokoro-js / Transformers.js) --
//
// No server involved: the 82M-parameter ONNX model is downloaded straight
// from the Hugging Face Hub by the browser and cached there (Cache Storage,
// managed by kokoro-js/Transformers.js), then every synthesis runs as local
// WebGPU/WASM inference. This is RION's PRIMARY voice; BrowserTTSProvider
// above is the fallback if the model can't load or generate.

const KOKORO_MODEL_ID = "onnx-community/Kokoro-82M-v1.0-ONNX";
export const KOKORO_DEFAULT_VOICE = "af_heart";

export type KokoroLoadState = "idle" | "loading" | "ready" | "error";

let kokoroState: KokoroLoadState = "idle";
let kokoroProgress = 0;
const kokoroStateListeners = new Set<(s: KokoroLoadState) => void>();

function setKokoroState(state: KokoroLoadState, progress?: number): void {
  kokoroState = state;
  if (progress !== undefined) kokoroProgress = progress;
  for (const fn of kokoroStateListeners) fn(state);
}

/** Current state of the on-device voice model — for first-use loading UI only. */
export function getKokoroLoadState(): KokoroLoadState {
  return kokoroState;
}

/** 0–100. Best-effort; only meaningful while state is "loading". */
export function getKokoroLoadProgress(): number {
  return kokoroProgress;
}

export function onKokoroLoadStateChange(fn: (s: KokoroLoadState) => void): () => void {
  kokoroStateListeners.add(fn);
  return () => kokoroStateListeners.delete(fn);
}

// Loaded once per session and reused for every synthesis — never re-created
// per message. A held promise (rather than the resolved instance) means
// concurrent first calls share one download instead of racing to start it.
type KokoroInstance = Awaited<ReturnType<typeof import("kokoro-js").KokoroTTS.from_pretrained>>;
type KokoroVoiceId = Parameters<KokoroInstance["generate"]>[1] extends { voice?: infer V }
  ? V
  : never;
let modelPromise: Promise<KokoroInstance> | null = null;

function supportsWebGPU(): boolean {
  return typeof navigator !== "undefined" && "gpu" in navigator;
}

function loadKokoroModel(): Promise<KokoroInstance> {
  if (modelPromise) return modelPromise;

  setKokoroState("loading", 0);
  modelPromise = (async () => {
    // Dynamic import: this ~ tens-of-MB library and its WASM/ONNX runtime
    // must never be part of the initial chat bundle or the SSR bundle. It
    // only ever loads client-side, and only on first mic/speaker use.
    const { KokoroTTS } = await import("kokoro-js");
    const webgpu = supportsWebGPU();
    return KokoroTTS.from_pretrained(KOKORO_MODEL_ID, {
      // WebGPU is recommended with fp32; WASM uses the smaller q8 quantization
      // so the one-time download stays reasonable on CPU-only devices.
      dtype: webgpu ? "fp32" : "q8",
      device: webgpu ? "webgpu" : "wasm",
      progress_callback: (info: { status: string; progress?: number }) => {
        if (info.status === "progress" && typeof info.progress === "number") {
          setKokoroState("loading", Math.max(kokoroProgress, Math.round(info.progress)));
        }
      },
    });
  })();

  modelPromise.then(
    () => setKokoroState("ready", 100),
    () => {
      setKokoroState("error");
      modelPromise = null; // let the next synthesize() attempt retry
    },
  );

  return modelPromise;
}

class BlobSource implements AudioSource {
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

export class KokoroBrowserProvider implements TTSProvider {
  readonly id = "kokoro" as const;
  // Replaying an answer (speaker button) reuses its audio instead of
  // re-synthesising. Memory only, small, dropped on reload.
  private cache = new Map<string, Blob>();

  async synthesize(
    text: string,
    options: TTSOptions = {},
    signal?: AbortSignal,
  ): Promise<AudioSource> {
    const voice = options.voice ?? KOKORO_DEFAULT_VOICE;
    const speed = options.speed ?? 1;
    const key = `${voice}|${speed}|${text}`;
    const cached = this.cache.get(key);
    if (cached) {
      this.cache.delete(key);
      this.cache.set(key, cached);
      return new BlobSource(cached);
    }

    const model = await loadKokoroModel();
    if (signal?.aborted) throw new DOMException("Synthesis aborted", "AbortError");

    // `voice` is a free-form string at ORION's edges (TTSOptions); kokoro-js
    // types it as its own closed voice-id union, which a runtime value can't
    // satisfy statically. generate() itself validates and throws on an
    // unknown id, so this narrowing is safe.
    const raw = await model.generate(text, { voice: voice as KokoroVoiceId, speed });
    const blob = raw.toBlob();

    this.cache.set(key, blob);
    if (this.cache.size > CACHE_LIMIT) {
      const oldest = this.cache.keys().next().value;
      if (oldest !== undefined) this.cache.delete(oldest);
    }
    return new BlobSource(blob);
  }

  stop(): void {
    audioElement().pause();
  }
}
