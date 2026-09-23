# ORION voice output (text-to-speech)

Status 2026-09-22: provider abstraction, Kokoro proxy, browser fallback and
voice preview are built and tested. **Deployed provider: `browser`** (no new
infrastructure). Kokoro has been run and verified locally only.

## 1. Architecture

```text
answer (markdown)
   │  sanitizeForSpeech()      src/lib/ai/speech-text.ts
   ▼  splitIntoSpeechChunks()  short first chunk, ~280-char chunks after
ttsService.speak()             src/lib/ai/tts.ts  ← the ONLY API the UI calls
   │  AudioManager: request ids, prefetch next chunk, fallback, interrupt
   ├─► KokoroTTSProvider ──POST /tts/speech──► FastAPI (auth) ──► Kokoro /v1/audio/speech
   │        (MP3 blob → shared <audio> element)   backend/app/api/tts.py
   └─► BrowserTTSProvider  (SpeechSynthesis — fallback, and the current default)
```

- **Provider selection** is server-side: `GET /tts/config` returns
  `TTS_PROVIDER`, the voice allowlist and defaults. Switching providers is an
  env change on the API; no frontend rebuild, no UI change.
- **Why a proxy:** Kokoro servers have no authentication. `/tts/speech`
  only synthesises for a signed-in ORION user (session verified against
  Supabase, cached 60 s per token hash), and `KOKORO_BASE_URL` never reaches
  the browser, so Kokoro can sit on a private network.
- **Fallback:** if Kokoro can't synthesise *or* its audio won't play, that
  chunk and the rest of the answer use the browser voice, and Kokoro is
  skipped for 60 s. Only if the browser voice also fails does `speak()`
  return `"failed"`; the text answer is never affected.
- **Interruptions:** every `speak()`/`stop()` bumps a request id. Anything
  async (a synthesis in flight, a prefetched chunk, a playing source) checks
  its id and stops/disposes if it's stale — so two ORION voices can never
  overlap, and an old answer can't start talking after a new question. The
  mic, a new question, the voice-mode orb and the Stop buttons all call it.
- **Orb sync (voice mode):** `processing` (thinking) lasts until audio
  actually starts (`onStart`), then `responding` while it plays, then idle.
  Playback failure shows `error` for 4 s, then idle.
- **Caching:** the Kokoro provider keeps the last 40 synthesised chunks in
  memory, so replaying an answer doesn't re-synthesise it.

## 2. Configuration (API environment)

| Variable | Default | Notes |
|---|---|---|
| `TTS_PROVIDER` | `browser` | `browser` or `kokoro` |
| `KOKORO_BASE_URL` | `http://localhost:8880` | Any Kokoro server implementing OpenAI's `POST /v1/audio/speech` |
| `KOKORO_VOICE` | `af_heart` | Must be in the allowlist below (checked at startup) |
| `KOKORO_SPEED` | `1.0` | Clamped to 0.7–1.3 |

Voice allowlist (`backend/app/api/tts.py`): `af_heart af_bella af_nicole
af_sarah af_sky am_adam am_michael bm_george bf_emma`. **`af_heart`
(American English) is RION's chosen default voice** — settled after
auditioning the set in Settings → RION's voice, which still lets anyone
override it for their own device via the same Preview button.

## 3. Running Kokoro locally

Kokoro servers listen on port 8000 by default, which is ORION's API port, so
map it to 8880.

```bash
# Apple Silicon / arm64 or x86-64, CPU only (verified on an M4, 2026-09-22):
docker run -d --name orion-kokoro -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest

# x86-64 only (no arm64 image published): the OpenTTSGroup server
docker run -d --name orion-kokoro -p 8880:8000 -e KOKORO_DEVICE=cpu \
  -v "$PWD/cache:/root/.cache" ghcr.io/openttsgroup/kokoro-open-tts:latest
```

Both expose the same OpenAI-compatible endpoint, which is all ORION uses.
Then in `.env`: `TTS_PROVIDER=kokoro` and restart `uvicorn`.

Measured locally (M4, Docker VM with 10 CPUs): image 4.55 GB; ~1.4 GiB RAM
after warm-up; first short chunk ("Your next class is Maths.") ~0.5 s;
a ~6 s sentence 1.4–2.3 s depending on voice.

## 4. Deploying Kokoro later — requirements and cost

Nothing here is provisioned. The deployed prototype uses `browser`.

- **Memory is the constraint:** ~1.4 GiB resident, so it needs an instance
  with **≥ 2 GB RAM**. Render free/starter (512 MB) cannot run it.
- **No GPU needed.** CPU synthesis is already faster than real time for
  sentence-sized chunks.
- **Always-on vs. cold start:** the model loads in seconds but a sleeping
  free-tier style instance would add that to the first spoken reply. The
  fallback covers it (the browser voice speaks instead), but for a
  consistent voice it should stay warm.
- **Cost:** any ≥ 2 GB always-on instance is a paid tier on every common
  host — expect a recurring monthly cost (roughly single to low double
  digits USD/month on small VPS or PaaS plans; check current pricing before
  choosing). This is a new paid service and needs an explicit decision.
- **Network:** keep Kokoro private (same private network as the API, or
  firewalled to the API's egress IP). It has no auth of its own.
- **Region:** put it next to the API — each chunk is a separate round trip.

To switch: deploy Kokoro, set `TTS_PROVIDER=kokoro` and `KOKORO_BASE_URL` on
the API service. Nothing else changes.

## 5. Mobile behaviour

- **Autoplay:** browsers only start audio from a user gesture, and an answer
  arrives seconds after the tap. `ttsService.unlock()` runs synchronously in
  every relevant tap (mic, send, suggestion, speaker, orb, preview) and plays
  50 ms of silence on the single shared `<audio>` element (plus an empty
  utterance for SpeechSynthesis). iOS Safari and Android Chrome then allow
  that element to play later answers without a new gesture.
- If a browser still blocks playback, the chunk falls back to the browser
  voice; if that's blocked too, voice mode shows an error and the answer
  text stays on screen.
- The mic always stops ORION speaking before listening, so it doesn't
  transcribe its own voice.

## 6. Known limitations

- **Voice input** uses the Web Speech API: Chrome, Edge and Safari only. Not
  Firefox (desktop or Android) — voice mode is unavailable there; typed chat
  and spoken answers still work.
- **iOS audio after dictation:** on some iOS versions, audio played right
  after speech recognition comes out quieter until the audio session resets.
  WebKit behaviour; not something the page can control.
- **Browser fallback voice** is whatever the device provides; it will not
  match the Kokoro voice.
- **Not true streaming:** text arrives as one response and is spoken in
  sentence chunks (with prefetch). Kokoro's streaming endpoint isn't used.
- The orb does not react to live microphone volume (doing so would need a
  second microphone stream alongside speech recognition, which conflicts on
  iOS).
