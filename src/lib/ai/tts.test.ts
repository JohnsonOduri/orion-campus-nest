import { beforeEach, describe, expect, it, vi } from "vitest";

// tts.ts builds the real providers at import time; keep the network layer out.
vi.mock("@/lib/api-client", () => ({ apiGet: vi.fn(), apiPostBlob: vi.fn() }));

import { AudioManager, type PlaybackState } from "./tts";
import type { AudioSource, TTSProvider, TTSProviderId } from "./tts-providers";

const flush = () => new Promise((r) => setTimeout(r, 0));

class FakeSource implements AudioSource {
  stopped = false;
  disposed = false;
  private finishPlay: (() => void) | null = null;
  constructor(
    readonly provider: TTSProviderId,
    readonly text: string,
    private readonly log: string[],
    private readonly failPlay: boolean,
  ) {}
  play(): Promise<void> {
    this.log.push(`${this.provider}:${this.text}`);
    if (this.failPlay) return Promise.reject(new Error("NotAllowedError"));
    return new Promise((resolve) => {
      this.finishPlay = resolve;
    });
  }
  finish() {
    this.finishPlay?.();
  }
  pause() {}
  resume() {}
  stop() {
    this.stopped = true;
    this.finishPlay?.();
  }
  dispose() {
    this.disposed = true;
  }
}

class FakeProvider implements TTSProvider {
  sources: FakeSource[] = [];
  failSynth = false;
  failPlay = false;
  constructor(
    readonly id: TTSProviderId,
    private readonly log: string[],
  ) {}
  async synthesize(text: string): Promise<AudioSource> {
    if (this.failSynth) throw new Error("503");
    const s = new FakeSource(this.id, text, this.log, this.failPlay);
    this.sources.push(s);
    return s;
  }
  stop() {}
}

/** Lets each chunk play to completion as soon as it starts. */
async function playThrough(...providers: FakeProvider[]) {
  for (let i = 0; i < 50; i++) {
    await flush();
    for (const p of providers) for (const s of p.sources) s.finish();
  }
}

const ANSWER =
  "Your next class is Maths. It starts at 10 AM in Lab 3. Dr. Rao is teaching it today.";

let log: string[];
let browser: FakeProvider;
let neural: FakeProvider;
let now: number;
let provider: TTSProviderId;
let manager: AudioManager;
let states: PlaybackState[];

beforeEach(() => {
  log = [];
  browser = new FakeProvider("browser", log);
  neural = new FakeProvider("kokoro", log);
  now = 1_000;
  provider = "kokoro";
  manager = new AudioManager(
    browser,
    neural,
    async () => ({ provider, options: { voice: "af_heart", speed: 1 } }),
    () => now,
  );
  states = [];
  manager.onStateChange((s) => states.push(s));
});

describe("AudioManager", () => {
  it("speaks every chunk in order with the neural voice", async () => {
    const onStart = vi.fn();
    const done = manager.speak(ANSWER, { onStart });
    await playThrough(neural);
    expect(await done).toBe("completed");
    expect(log.every((l) => l.startsWith("kokoro:"))).toBe(true);
    expect(log.map((l) => l.slice(7)).join(" ")).toBe(ANSWER);
    expect(onStart).toHaveBeenCalledTimes(1);
    expect(onStart).toHaveBeenCalledWith("kokoro");
    expect(states).toEqual(["loading", "speaking", "idle"]);
  });

  it("synthesises the next chunk while the current one plays", async () => {
    void manager.speak(ANSWER);
    await flush();
    await flush();
    expect(log).toHaveLength(1); // first chunk playing
    expect(neural.sources.length).toBe(2); // second already fetched
  });

  it("interrupt stops playback immediately and nothing else plays", async () => {
    const done = manager.speak(ANSWER);
    await flush();
    await flush();
    manager.interrupt();
    expect(await done).toBe("interrupted");
    expect(neural.sources[0]!.stopped).toBe(true);
    await playThrough(neural);
    expect(log).toHaveLength(1);
    expect(manager.getState()).toBe("idle");
    expect(neural.sources.every((s) => s.disposed)).toBe(true);
  });

  it("a newer answer silences the older one — never two voices", async () => {
    const first = manager.speak("Old answer one. Old answer two is also quite long indeed.");
    await flush();
    await flush();
    const second = manager.speak("New answer here, which is the one we want.");
    expect(await first).toBe("interrupted");
    await playThrough(neural);
    expect(await second).toBe("completed");
    expect(log.filter((l) => l.includes("Old"))).toHaveLength(1);
    expect(log.at(-1)).toContain("New answer");
  });

  it("falls back to the browser voice when Kokoro can't synthesise", async () => {
    neural.failSynth = true;
    const onFallback = vi.fn();
    manager.onFallback(onFallback);
    const done = manager.speak(ANSWER);
    await playThrough(browser, neural);
    expect(await done).toBe("completed");
    expect(log.every((l) => l.startsWith("browser:"))).toBe(true);
    expect(onFallback).toHaveBeenCalledTimes(1);
  });

  it("doesn't retry a failing Kokoro on every answer, but does after a cooldown", async () => {
    neural.failSynth = true;
    const a = manager.speak("First answer is here.");
    await playThrough(browser);
    await a;

    neural.failSynth = false;
    const b = manager.speak("Second answer is here.");
    await playThrough(browser, neural);
    await b;
    expect(neural.sources).toHaveLength(0);

    now += 61_000;
    const c = manager.speak("Third answer is here.");
    await playThrough(browser, neural);
    await c;
    expect(neural.sources.length).toBeGreaterThan(0);
  });

  it("replays a chunk with the browser voice if Kokoro audio won't play", async () => {
    neural.failPlay = true;
    const done = manager.speak("Your next class is Maths at ten.");
    await playThrough(browser);
    expect(await done).toBe("completed");
    expect(log).toEqual([
      "kokoro:Your next class is Maths at ten.",
      "browser:Your next class is Maths at ten.",
    ]);
  });

  it("reports failure (and returns to idle) when no voice can play", async () => {
    neural.failSynth = true;
    browser.failPlay = true;
    const done = manager.speak("Hello there, this should fail.");
    await playThrough(browser);
    expect(await done).toBe("failed");
    expect(manager.getState()).toBe("idle");
  });

  it("uses only the browser voice when the server says so", async () => {
    provider = "browser";
    const done = manager.speak(ANSWER);
    await playThrough(browser);
    expect(await done).toBe("completed");
    expect(neural.sources).toHaveLength(0);
  });

  it("does nothing for text with nothing speakable", async () => {
    expect(await manager.speak("```js\nx()\n```")).toBe("completed");
    expect(log).toEqual([]);
    expect(states).toEqual([]);
  });
});
