import { useEffect, useState } from "react";
import { Play, RotateCcw, Square } from "lucide-react";
import { SectionCard } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { ttsService, type PlaybackState } from "@/lib/ai/tts";
import type { TTSProviderId } from "@/lib/ai/tts-providers";
import {
  loadTtsConfig,
  readVoicePrefs,
  resolveVoiceOptions,
  writeVoicePrefs,
  type TTSServerConfig,
} from "@/lib/ai/voice-settings";

const SAMPLE =
  "Hi, I'm RION. I can help you find information about your classes, timetable, faculty and campus.";

// Lets a person audition voices and pick one without code changes. The
// server's default (KOKORO_VOICE / KOKORO_SPEED) applies until they choose.
export function VoiceSettingsCard() {
  const [config, setConfig] = useState<TTSServerConfig | null>(null);
  const [voice, setVoice] = useState<string>("");
  const [speed, setSpeed] = useState(1);
  const [playback, setPlayback] = useState<PlaybackState>("idle");
  const [previewing, setPreviewing] = useState(false);
  const [playedWith, setPlayedWith] = useState<TTSProviderId | null>(null);

  useEffect(() => {
    let active = true;
    void loadTtsConfig().then((c) => {
      if (!active) return;
      const resolved = resolveVoiceOptions(c, readVoicePrefs());
      setConfig(c);
      setVoice(resolved.voice);
      setSpeed(resolved.speed);
    });
    const off = ttsService.onStateChange((s) => {
      setPlayback(s);
      if (s === "idle") setPreviewing(false);
    });
    return () => {
      active = false;
      off();
      ttsService.stop();
    };
  }, []);

  function save(next: { voice?: string; speed?: number }) {
    const prefs = { ...readVoicePrefs(), ...next };
    writeVoicePrefs(prefs);
  }

  function preview() {
    ttsService.unlock();
    if (previewing) {
      ttsService.stop();
      return;
    }
    ttsService.stop();
    setPreviewing(true);
    setPlayedWith(null);
    void ttsService.speak(SAMPLE, { voice, speed, onStart: setPlayedWith });
  }

  function reset() {
    if (!config) return;
    writeVoicePrefs({});
    setVoice(config.default_voice);
    setSpeed(config.default_speed);
  }

  const neural = config?.provider === "kokoro";
  const [minSpeed, maxSpeed] = config?.speed_range ?? [0.7, 1.3];

  return (
    <SectionCard title="RION's voice" description="How RION sounds when it reads answers aloud.">
      <div className="space-y-5">
        <p className="rounded-xl bg-muted px-3 py-2.5 text-xs text-muted-foreground">
          {config === null
            ? "Checking voice service…"
            : neural
              ? "Neural voice (Kokoro) is enabled. If it can't be reached, RION falls back to your device's voice."
              : "RION is currently using your device's built-in voice. Voice choices below apply once the neural voice is enabled on the server."}
        </p>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="orion-voice">Voice</Label>
            <Select
              value={voice}
              onValueChange={(v) => {
                setVoice(v);
                save({ voice: v });
              }}
              disabled={!config || config.voices.length === 0}
            >
              <SelectTrigger id="orion-voice" className="h-11 rounded-xl">
                <SelectValue placeholder="Default" />
              </SelectTrigger>
              <SelectContent>
                {config?.voices.map((v) => (
                  <SelectItem key={v.id} value={v.id}>
                    {v.name} · {v.accent} {v.gender}
                    {v.id === config.default_voice ? " (default)" : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="orion-speed">Speed</Label>
              <span className="font-mono text-xs text-muted-foreground">{speed.toFixed(2)}×</span>
            </div>
            <Slider
              id="orion-speed"
              min={minSpeed}
              max={maxSpeed}
              step={0.05}
              value={[speed]}
              onValueChange={([v]) => v !== undefined && setSpeed(v)}
              onValueCommit={([v]) => v !== undefined && save({ speed: v })}
              aria-label="Speaking speed"
              className="py-3"
            />
          </div>
        </div>

        <blockquote className="border-l-2 border-primary/40 pl-3 text-sm text-muted-foreground italic">
          “{SAMPLE}”
        </blockquote>

        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={preview} disabled={!config} className="h-11 gap-2 rounded-full px-5">
            {previewing ? <Square className="size-4" /> : <Play className="size-4" />}
            {previewing ? (playback === "loading" ? "Preparing…" : "Stop") : "Preview"}
          </Button>
          <Button
            variant="ghost"
            onClick={reset}
            disabled={!config}
            className="h-11 gap-2 rounded-full"
          >
            <RotateCcw className="size-4" /> Reset to default
          </Button>
          {playedWith ? (
            <span className="text-xs text-muted-foreground" aria-live="polite">
              {playedWith === "kokoro"
                ? `Playing Kokoro · ${voice}`
                : "Playing your device's voice"}
            </span>
          ) : null}
        </div>
      </div>
    </SectionCard>
  );
}
