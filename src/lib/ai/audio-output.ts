// The one <audio> element all synthesised speech plays through.
//
// Mobile browsers (iOS Safari especially) only allow audio to start from a
// user gesture. A voice answer arrives seconds after the tap that asked for
// it, so playing a fresh element then would be blocked. Instead, `unlock()`
// is called synchronously inside the tap (mic, send, speaker button) and
// plays a few milliseconds of silence on this element; after that, Safari
// and Chrome let the same element play new sources without a gesture.
// SpeechSynthesis gets the same treatment with an empty utterance.

let element: HTMLAudioElement | null = null;
let unlocked = false;
let silentUrl: string | null = null;

function silentWavUrl(): string {
  if (silentUrl) return silentUrl;
  const sampleRate = 8000;
  const samples = 400; // 50 ms
  const buffer = new ArrayBuffer(44 + samples * 2);
  const view = new DataView(buffer);
  const writeStr = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + samples * 2, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, samples * 2, true);
  silentUrl = URL.createObjectURL(new Blob([buffer], { type: "audio/wav" }));
  return silentUrl;
}

export function audioElement(): HTMLAudioElement {
  if (!element) {
    element = new Audio();
    element.preload = "auto";
    element.setAttribute("playsinline", "");
    element.setAttribute("webkit-playsinline", "");
  }
  return element;
}

/** Call synchronously from a click/tap handler, before any await. Safe to call repeatedly. */
export function unlockAudio(): void {
  if (typeof window === "undefined" || unlocked) return;
  const el = audioElement();
  el.src = silentWavUrl();
  el.play()
    .then(() => {
      unlocked = true;
    })
    .catch(() => {
      // Not a gesture, or blocked by the browser — the next real tap retries.
    });

  if ("speechSynthesis" in window) {
    const warmup = new SpeechSynthesisUtterance("");
    warmup.volume = 0;
    window.speechSynthesis.speak(warmup);
  }
}

export function isAudioUnlocked(): boolean {
  return unlocked;
}
