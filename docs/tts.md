# ORION voice output (text-to-speech)

Status 2026-09-23: RION's voice runs **entirely in the browser**. There is no
Kokoro server, no TTS proxy endpoint, and no backend TTS configuration —
zero additional infrastructure, zero additional cost.

## 1. Architecture

```text
answer (markdown)
   │  sanitizeForSpeech()      src/lib/ai/speech-text.ts
   ▼  splitIntoSpeechChunks()  short first chunk, ~280-char chunks after
ttsService.speak()             src/lib/ai/tts.ts  ← the ONLY API the UI calls
   │  AudioManager: request ids, prefetch next chunk, fallback, interrupt
   ├─► KokoroBrowserProvider ──kokoro-js (Transformers.js/ONNX)──► on-device inference
   │        (WAV Blob → shared <audio> element)   src/lib/ai/tts-providers.ts
   └─► BrowserTTSProvider  (SpeechSynthesis — fallback)
```

- **Provider is fixed, not configurable**: `kokoro` (on-device) is primary,
  `browser` (SpeechSynthesis) is the automatic fallback. There is nothing to
  switch server-side because there is no server involved — `src/lib/ai/tts.ts`
  hard-codes voice `af_heart`, language `en-US`, speed `1.0`
  (`KOKORO_DEFAULT_VOICE` in `tts-providers.ts`). `VoiceSettingsCard`
  (`src/components/ai/voice-settings-card.tsx`) is a preview button only —
  there is no voice/speed picker, because there is nothing to pick.
- **Model**: [`onnx-community/Kokoro-82M-v1.0-ONNX`](https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX)
  loaded via the [`kokoro-js`](https://www.npmjs.com/package/kokoro-js)
  package, which wraps 🤗 Transformers.js. The browser downloads the model
  from the Hugging Face Hub directly (cached in the browser's Cache Storage
  by Transformers.js) and every synthesis after that is local inference —
  WebGPU if `navigator.gpu` exists, WASM otherwise. Neither path involves
  ORION's servers.
- **Lazy, singleton load**: the model is imported (`await import("kokoro-js")`,
  dynamic — never in the initial chat bundle or the SSR bundle) and
  instantiated only on the first call to `KokoroBrowserProvider.synthesize()`,
  i.e. the first time a person taps the mic or the speaker icon. The loading
  promise is cached module-scope (`tts-providers.ts`), so every later
  question in the same tab reuses the already-loaded model — `new
  KokoroTTS(...)` never runs twice.
- **First-use loading UX**: `getKokoroLoadState()` /
  `onKokoroLoadStateChange()` expose `"idle" | "loading" | "ready" | "error"`
  (plus a best-effort 0–100 `getKokoroLoadProgress()` from Transformers.js's
  `progress_callback`). `AiChatPanel` (`src/components/ai/ai-chat.tsx`)
  subscribes and shows a toast — "Preparing RION's voice…" then "RION is
  ready." — the first time only, gated on a `localStorage` flag
  (`orion-voice-primed`) so it never repeats on that device. No ONNX/WASM/
  WebGPU jargon reaches the user.
- **Fallback:** if the model fails to load, or `generate()` throws, that
  chunk and the rest of the answer use the browser voice, and Kokoro is
  skipped for 60 s (same circuit-breaker as before — `AudioManager` in
  `tts.ts`, unchanged). Only if the browser voice also fails does `speak()`
  return `"failed"`; the text answer is never affected.
- **Interruptions:** unchanged — every `speak()`/`stop()` bumps a request id;
  anything async (a synthesis in flight, a prefetched chunk, a playing
  source) checks its id and stops/disposes if it's stale, so two ORION voices
  can never overlap and an old answer can't start talking after a new one.
- **Orb sync (voice mode):** unchanged — `processing` (thinking) lasts until
  audio actually starts (`onStart`), then `responding` while it plays, then
  idle. Playback failure shows `error` for 4 s, then idle.
- **Caching:** `KokoroBrowserProvider` keeps the last 40 synthesised chunks
  (as WAV `Blob`s) in memory per tab, so replaying an answer doesn't
  re-synthesise it. The model itself is cached by the browser across
  sessions (Cache Storage), so it isn't re-downloaded on every visit either.

## 2. Why this replaced the server-proxied Kokoro design

The previous design (`backend/app/api/tts.py`, removed 2026-09-23) proxied
`POST /tts/speech` to a Kokoro server (`KOKORO_BASE_URL`) so the browser
never talked to an unauthenticated Kokoro instance directly. That Kokoro
server was never actually deployed (docs/tts.md previously documented it as
"nothing provisioned") because it needs ≥2 GB RAM, which is a paid tier on
every common host — a real recurring cost for a prototype meant to stay near
zero. Running the model in the browser instead removes the server (and its
cost and its auth surface) entirely: there's no `KOKORO_API_KEY`, no
`KOKORO_URL`, no `KOKORO_SERVER` — the backend has no TTS configuration at
all.

## 3. What runs where

```text
No new infra. No GPU server. No paid TTS API. No Kokoro server.
Model inference happens on the visitor's own device, in their browser tab.
```

The Render backend performs no TTS work and forwards no answer text to any
TTS API — see `backend/app/core/ratelimit.py` (no `TTS_LIMITER` — only
`ASK_LIMITER` for `/ai/ask`) and `backend/app/core/config.py` (no
`TTS_PROVIDER`/`KOKORO_*`).

## 4. Mobile behaviour

- **Autoplay:** browsers only start audio from a user gesture, and an answer
  arrives seconds after the tap. `ttsService.unlock()` runs synchronously in
  every relevant tap (mic, send, suggestion, speaker, orb, preview) and plays
  50 ms of silence on the single shared `<audio>` element (plus an empty
  utterance for SpeechSynthesis). iOS Safari and Android Chrome then allow
  that element to play later answers without a new gesture. This is
  unaffected by the browser-Kokoro change — the model produces a `Blob`
  that plays through the same unlocked element as before.
- If a browser can't run Kokoro (WebGPU and WASM both unavailable/blocked,
  or the model fails to load), the chunk falls back to the browser voice; if
  that's blocked too, voice mode shows an error and the answer text stays on
  screen.
- The mic always stops ORION speaking before listening, so it doesn't
  transcribe its own voice.
- **First-visit cost:** the model download (tens of MB) happens once per
  device on first voice use, not on page load, and is browser-cached after
  that. On a slow connection this can take a while — the "Preparing RION's
  voice…" toast covers exactly that window, and text chat is fully usable
  the entire time since the model load is never on the critical path for
  displaying an answer.

## 5. Known limitations

- **Voice input** uses the Web Speech API: Chrome, Edge and Safari only. Not
  Firefox (desktop or Android) — voice mode is unavailable there; typed chat
  and spoken answers still work.
- **iOS audio after dictation:** on some iOS versions, audio played right
  after speech recognition comes out quieter until the audio session resets.
  WebKit behaviour; not something the page can control.
- **Browser fallback voice** is whatever the device provides; it will not
  match the Kokoro voice.
- **Not true streaming:** text arrives as one response and is spoken in
  sentence chunks (with prefetch). `kokoro-js`'s own streaming API
  (`TextSplitterStream`/`tts.stream()`) isn't used — chunk-level prefetch
  already hides the gap between sentences, and per-chunk `generate()` is
  simpler to reason about with the existing interruption/staleness model.
- Low-end or older devices without WebGPU fall back to WASM, which is
  noticeably slower per chunk; very old/low-memory devices may fail to load
  the model at all, in which case the automatic browser-voice fallback
  covers it.
- The orb does not react to live microphone volume (doing so would need a
  second microphone stream alongside speech recognition, which conflicts on
  iOS).
