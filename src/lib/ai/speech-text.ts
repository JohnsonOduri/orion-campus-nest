// Turns an assistant answer (markdown) into text that sounds right when read
// aloud. Pure string transforms — no DOM or markdown parser — because the
// inputs are ORION's own short answers, not arbitrary documents.
//
// Never spoken: markdown syntax, URLs, code blocks, JSON, citations
// ("[Doc — Section]", "(source: ...)"), UUIDs and other internal IDs, emoji.

const UUID_RE = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi;
const LONG_HEX_RE = /\b[0-9a-f]{16,}\b/gi;
const EMOJI_RE = /[\p{Extended_Pictographic}\u{FE0F}\u{200D}]/gu;
const ENDS_WITH_PUNCTUATION = /[.!?:;,]$/;

function withPause(line: string): string {
  return ENDS_WITH_PUNCTUATION.test(line) ? line : `${line}.`;
}

function cleanInline(text: string): string {
  let t = text;
  t = t.replace(/!\[[^\]]*\]\([^)]*\)/g, ""); // images
  t = t.replace(/\[([^\]]+)\]\((?:[^)]+)\)/g, "$1"); // [label](url) -> label
  t = t.replace(/\[[^\]]*\]/g, ""); // citations like [Regulations — Attendance] or [1]
  t = t.replace(/\((?:source|sources|ref|id)\s*:[^)]*\)/gi, "");
  t = t.replace(/https?:\/\/\S+|www\.\S+/gi, "the link shown in the chat");
  t = t.replace(/`([^`]+)`/g, "$1");
  t = t.replace(/\*\*(.+?)\*\*|__(.+?)__/g, (_, a, b) => a ?? b);
  t = t.replace(/(^|[\s(])[*_](\S(?:.*?\S)?)[*_](?=[\s).,!?;:]|$)/g, "$1$2");
  t = t.replace(/~~(.+?)~~/g, "$1");
  t = t.replace(UUID_RE, "").replace(LONG_HEX_RE, "");
  t = t.replace(EMOJI_RE, "");
  // "10:00 AM" reads more naturally as "10 AM".
  t = t.replace(/\b(\d{1,2}):00\s*([ap])\.?m\.?\b/gi, (_, h, ap) => `${h} ${ap.toUpperCase()}M`);
  t = t.replace(
    /\b(\d{1,2}:\d{2})\s*([ap])\.?m\.?\b/gi,
    (_, hm, ap) => `${hm} ${ap.toUpperCase()}M`,
  );
  t = t.replace(/\s*&\s*/g, " and ");
  t = t.replace(/[ \t]{2,}/g, " ");
  return t.trim();
}

/** Strips markdown and anything not meant to be spoken, keeping natural pauses. */
export function sanitizeForSpeech(markdown: string): string {
  let text = markdown.replace(/\r\n?/g, "\n");

  text = text.replace(/```[\s\S]*?```/g, "\n"); // fenced code: never read aloud
  text = text.replace(/^\s*[*_]?\s*(sources?|via)\s*:.*$/gim, ""); // citation footer lines
  text = text.replace(/^(?: {4}|\t).*$/gm, ""); // indented code
  text = text.replace(/\{[^{}]*"[^"]*"\s*:[^{}]*\}/g, ""); // inline JSON objects

  const spoken: string[] = [];
  for (const raw of text.split("\n")) {
    let line = raw.trim();
    if (!line) continue;
    if (/^\|?\s*:?-{2,}/.test(line) && /^[\s|:-]+$/.test(line)) continue; // table separator
    if (/^([-*_])\s*(\1\s*){2,}$/.test(line)) continue; // horizontal rule

    line = line.replace(/^#{1,6}\s+/, ""); // headings become their own sentence below
    line = line.replace(/^>\s?/, "");
    line = line.replace(/^(?:[-*+]|\d+[.)])\s+/, "");
    line = line.replace(/^\[[ xX]\]\s+/, "");
    if (line.includes("|")) {
      line = line
        .split("|")
        .map((cell) => cell.trim())
        .filter(Boolean)
        .join(", ");
    }

    line = cleanInline(line);
    if (!line || !/[\p{L}\p{N}]/u.test(line)) continue;
    spoken.push(withPause(line));
  }

  return spoken
    .join(" ")
    .replace(/\s+([.,!?;:])/g, "$1")
    .replace(/([.!?])\s*\.+/g, "$1")
    .replace(/,\s*\./g, ".")
    .replace(/\s{2,}/g, " ")
    .trim();
}

const ABBREVIATIONS =
  /\b(?:Dr|Mr|Mrs|Ms|Prof|Sr|Jr|St|vs|etc|e\.g|i\.e|No|Fig|Sec|Dept|approx)\.$/i;

/** Splits into sentences without breaking on "Dr." or "3.5". */
export function splitSentences(text: string): string[] {
  const sentences: string[] = [];
  let current = "";
  const tokens = text.split(/(\s+)/);
  for (const token of tokens) {
    current += token;
    if (/[.!?]["')\]]?$/.test(token) && !ABBREVIATIONS.test(token)) {
      if (current.trim()) sentences.push(current.trim());
      current = "";
    }
  }
  if (current.trim()) sentences.push(current.trim());
  return sentences;
}

/**
 * Groups sentences into chunks for synthesis. The first chunk is kept short
 * so audio starts quickly; later chunks are larger because neural TTS sounds
 * more natural with a full sentence group, and they're prefetched while the
 * previous chunk plays anyway.
 */
export function splitIntoSpeechChunks(text: string, maxChars = 280): string[] {
  const sentences = splitSentences(text);
  const chunks: string[] = [];
  let current = "";
  for (const sentence of sentences) {
    const isFirstChunk = chunks.length === 0;
    const limit = isFirstChunk ? 40 : maxChars;
    if (!current) {
      current = sentence;
    } else if (current.length + 1 + sentence.length <= limit || current.length < 25) {
      current = `${current} ${sentence}`;
    } else {
      chunks.push(current);
      current = sentence;
    }
    while (current.length > maxChars) {
      const cut = Math.max(
        current.lastIndexOf(", ", maxChars),
        current.lastIndexOf("; ", maxChars),
      );
      const at = cut > 40 ? cut + 1 : current.lastIndexOf(" ", maxChars);
      if (at <= 0) break;
      chunks.push(current.slice(0, at).trim());
      current = current.slice(at).trim();
    }
  }
  if (current) chunks.push(current);
  return chunks;
}
