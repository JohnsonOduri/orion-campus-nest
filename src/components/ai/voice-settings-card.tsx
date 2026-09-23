import { useEffect, useState } from "react";
import { Play, Square } from "lucide-react";
import { SectionCard } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { ttsService, type PlaybackState } from "@/lib/ai/tts";

const SAMPLE =
  "Hi, I'm RION. I can help you find information about your classes, timetable, faculty and campus.";

// RION's voice is fixed (kokoro-js, af_heart, running on-device — see
// src/lib/ai/tts-providers.ts) rather than a per-user setting, so this is
// just a way to hear it and confirm it works on this device. No voice or
// speed picker: there is nothing to choose.
export function VoiceSettingsCard() {
  const [playback, setPlayback] = useState<PlaybackState>("idle");
  const [previewing, setPreviewing] = useState(false);

  useEffect(() => {
    const off = ttsService.onStateChange((s) => {
      setPlayback(s);
      if (s === "idle") setPreviewing(false);
    });
    return () => {
      off();
      ttsService.stop();
    };
  }, []);

  function preview() {
    ttsService.unlock();
    if (previewing) {
      ttsService.stop();
      return;
    }
    ttsService.stop();
    setPreviewing(true);
    void ttsService.speak(SAMPLE);
  }

  return (
    <SectionCard title="RION's voice" description="How RION sounds when it reads answers aloud.">
      <div className="space-y-5">
        <p className="rounded-xl bg-muted px-3 py-2.5 text-xs text-muted-foreground">
          RION speaks with its own voice, generated on your device. The first time it speaks it
          takes a moment to get ready; after that it's instant. If it can't run on this device, RION
          falls back to your device's built-in voice.
        </p>

        <blockquote className="border-l-2 border-primary/40 pl-3 text-sm text-muted-foreground italic">
          “{SAMPLE}”
        </blockquote>

        <Button onClick={preview} className="h-11 gap-2 rounded-full px-5">
          {previewing ? <Square className="size-4" /> : <Play className="size-4" />}
          {previewing ? (playback === "loading" ? "Preparing…" : "Stop") : "Preview"}
        </Button>
      </div>
    </SectionCard>
  );
}
