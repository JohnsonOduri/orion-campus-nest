import { apiGet } from "@/lib/api-client";
import type { TTSOptions, TTSProviderId } from "./tts-providers";

// Which provider to use and the voice defaults come from the backend
// (TTS_PROVIDER / KOKORO_VOICE / KOKORO_SPEED — see docs/tts.md), so switching
// to Kokoro is an env change, not a frontend rebuild. A person's own voice and
// speed choice is a per-device preference kept in localStorage.

export type VoiceInfo = { id: string; name: string; accent: string; gender: string };

export type TTSServerConfig = {
  provider: TTSProviderId;
  default_voice: string;
  default_speed: number;
  speed_range: [number, number];
  voices: VoiceInfo[];
};

const BROWSER_ONLY: TTSServerConfig = {
  provider: "browser",
  default_voice: "af_heart",
  default_speed: 1,
  speed_range: [0.7, 1.3],
  voices: [],
};

let configPromise: Promise<TTSServerConfig> | null = null;

export function loadTtsConfig(): Promise<TTSServerConfig> {
  if (!configPromise) {
    configPromise = apiGet<TTSServerConfig>("/tts/config").catch(() => {
      configPromise = null; // retry on the next call instead of caching the failure
      return BROWSER_ONLY;
    });
  }
  return configPromise;
}

export type VoicePrefs = { voice?: string; speed?: number };

const PREFS_KEY = "orion-voice";

export function readVoicePrefs(): VoicePrefs {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as VoicePrefs;
    const prefs: VoicePrefs = {};
    if (typeof parsed.voice === "string") prefs.voice = parsed.voice;
    if (typeof parsed.speed === "number") prefs.speed = parsed.speed;
    return prefs;
  } catch {
    return {};
  }
}

export function writeVoicePrefs(prefs: VoicePrefs): void {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // Private mode / storage blocked: the choice just won't persist.
  }
}

export function resolveVoiceOptions(
  config: TTSServerConfig,
  prefs: VoicePrefs,
): Required<TTSOptions> {
  const known = config.voices.some((v) => v.id === prefs.voice);
  const [min, max] = config.speed_range;
  const speed = prefs.speed ?? config.default_speed;
  return {
    voice: known && prefs.voice ? prefs.voice : config.default_voice,
    speed: Math.min(max, Math.max(min, speed)),
  };
}
