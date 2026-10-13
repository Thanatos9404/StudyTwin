// Audio tutoring helpers built on the browser's Web Speech API (no extra service or key).
// Speech output works offline in most browsers; voice input uses the browser's own speech service.

const isHindi = (t: string) => /[ऀ-ॿ]/.test(t);

/** Turn a markdown + LaTeX answer into something a speech engine can read aloud. */
export function speakable(md: string): string {
  return md
    .replace(/\[S\d+\]/g, "")
    .replace(/\\frac\{([^}]*)\}\{([^}]*)\}/g, " $1 over $2 ")
    .replace(/\\mid|\|/g, " given ")
    .replace(/\\times|\\cdot/g, " times ")
    .replace(/\\cap/g, " and ")
    .replace(/\\cup/g, " or ")
    .replace(/\^\{?c\}?/g, " complement")
    .replace(/\\approx/g, " approximately ")
    .replace(/\\[a-zA-Z]+/g, " ")
    .replace(/\\\(|\\\)|\\\[|\\\]|\$\$?|[{}*#_`>]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export const canSpeak = () => typeof window !== "undefined" && "speechSynthesis" in window;

export function speak(text: string, onEnd?: () => void): void {
  if (!canSpeak()) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(speakable(text));
  u.lang = isHindi(text) ? "hi-IN" : "en-IN";
  u.rate = 1;
  if (onEnd) u.onend = onEnd;
  window.speechSynthesis.speak(u);
}

export function stopSpeaking(): void {
  if (canSpeak()) window.speechSynthesis.cancel();
}

type Recognition = {
  lang: string;
  interimResults: boolean;
  onresult: (e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void;
  onend: () => void;
  onerror: () => void;
  start: () => void;
  stop: () => void;
};

export function recognizer(): Recognition | null {
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  const C = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  return C ? new C() : null;
}
