// Speech-to-text, decoupled from any UI (spec §12). Browser-native
// SpeechRecognition only — no server-side ASR exists in ORION today, and
// adding one would be a much bigger backend change than this pass scoped.
// Callers must call `supported()` before rendering voice-input UI and
// degrade gracefully (spec: unsupported browsers never crash the chat).

type SpeechRecognitionCtor = new () => SpeechRecognition;

function getCtor(): SpeechRecognitionCtor | undefined {
  if (typeof window === "undefined") return undefined;
  return (
    (
      window as unknown as {
        SpeechRecognition?: SpeechRecognitionCtor;
        webkitSpeechRecognition?: SpeechRecognitionCtor;
      }
    ).SpeechRecognition ??
    (window as unknown as { webkitSpeechRecognition?: SpeechRecognitionCtor })
      .webkitSpeechRecognition
  );
}

export type VoiceInputError =
  "no-speech" | "not-allowed" | "network" | "aborted" | "unsupported" | "unknown";

export interface VoiceInputCallbacks {
  onTranscript?: (transcript: string, isFinal: boolean) => void;
  onEnd?: () => void;
  onError?: (error: VoiceInputError) => void;
}

export class VoiceInputService {
  private recognition: SpeechRecognition | null = null;
  private active = false;

  supported(): boolean {
    return !!getCtor();
  }

  start(callbacks: VoiceInputCallbacks, lang = "en-IN"): void {
    const Ctor = getCtor();
    if (!Ctor) {
      callbacks.onError?.("unsupported");
      return;
    }
    this.stop();

    const recognition = new Ctor();
    recognition.lang = lang;
    recognition.continuous = false;
    recognition.interimResults = true;

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let finalTranscript = "";
      let interimTranscript = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (!result) continue;
        if (result.isFinal) finalTranscript += result[0]?.transcript ?? "";
        else interimTranscript += result[0]?.transcript ?? "";
      }
      if (finalTranscript) callbacks.onTranscript?.(finalTranscript.trim(), true);
      else if (interimTranscript) callbacks.onTranscript?.(interimTranscript.trim(), false);
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      const map: Record<string, VoiceInputError> = {
        "no-speech": "no-speech",
        "not-allowed": "not-allowed",
        "service-not-allowed": "not-allowed",
        network: "network",
        aborted: "aborted",
      };
      callbacks.onError?.(map[event.error] ?? "unknown");
    };

    recognition.onend = () => {
      this.active = false;
      callbacks.onEnd?.();
    };

    this.recognition = recognition;
    this.active = true;
    recognition.start();
  }

  stop(): void {
    if (this.recognition && this.active) {
      this.recognition.stop();
    }
    this.recognition = null;
    this.active = false;
  }

  cancel(): void {
    if (this.recognition) {
      this.recognition.onresult = null;
      this.recognition.onerror = null;
      this.recognition.onend = null;
      if (this.active) this.recognition.abort();
    }
    this.recognition = null;
    this.active = false;
  }

  isActive(): boolean {
    return this.active;
  }
}

export const voiceInputService = new VoiceInputService();
