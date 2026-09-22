import { describe, expect, it } from "vitest";
import { sanitizeForSpeech, splitIntoSpeechChunks, splitSentences } from "./speech-text";

describe("sanitizeForSpeech", () => {
  it("turns the spec example into natural speech", () => {
    const md =
      "## Tomorrow\n\nYour **Data Structures** class is at **10:00 AM**.\n\nIt is in Lab 3.";
    expect(sanitizeForSpeech(md)).toBe(
      "Tomorrow. Your Data Structures class is at 10 AM. It is in Lab 3.",
    );
  });

  it("never speaks URLs, link targets or images", () => {
    const out = sanitizeForSpeech(
      "See [the handbook](https://iiitk.ac.in/handbook.pdf) or https://example.com/x?y=1 ![logo](a.png)",
    );
    expect(out).not.toMatch(/https?:|iiitk\.ac\.in|example\.com|png/);
    expect(out).toContain("the handbook");
  });

  it("drops code blocks and JSON", () => {
    const out = sanitizeForSpeech(
      'Here:\n\n```python\nprint("hi")\n```\n\nData {"id": 4, "room": "L3"} done.',
    );
    expect(out).not.toMatch(/print|"id"|room/);
    expect(out).toContain("Here:");
    expect(out).toContain("done.");
  });

  it("drops citations, source notes, UUIDs and emoji", () => {
    const out = sanitizeForSpeech(
      "- [UG Regulations 26 — Attendance] 75% attendance is required (source: documents)\n\n⚠️ entry 3f2a9c1e-1b2c-4d5e-8f90-123456789abc is stale",
    );
    expect(out).not.toMatch(/Regulations 26|source|3f2a9c1e|⚠/);
    expect(out).toContain("75% attendance is required.");
  });

  it("never reads the citation footer", () => {
    expect(
      sanitizeForSpeech(
        "Your next class is Maths.\n\n*Source: your live timetable; faculty directory*",
      ),
    ).toBe("Your next class is Maths.");
  });

  it("gives list items and headings a pause", () => {
    expect(sanitizeForSpeech("### Classes\n- Maths at 9 AM\n- Physics at 11 AM")).toBe(
      "Classes. Maths at 9 AM. Physics at 11 AM.",
    );
  });

  it("reads tables row by row without pipes", () => {
    const out = sanitizeForSpeech("| Day | Class |\n|---|---|\n| Mon | Maths |");
    expect(out).toBe("Day, Class. Mon, Maths.");
  });

  it("keeps identifiers with underscores intact inside words", () => {
    expect(sanitizeForSpeech("Use snake_case names.")).toBe("Use snake_case names.");
  });
});

describe("splitSentences", () => {
  it("does not split on abbreviations or decimals", () => {
    expect(splitSentences("Dr. Rao teaches it. It has 3.5 credits. Ask him!")).toEqual([
      "Dr. Rao teaches it.",
      "It has 3.5 credits.",
      "Ask him!",
    ]);
  });
});

describe("splitIntoSpeechChunks", () => {
  it("keeps the first chunk short so audio starts quickly", () => {
    const chunks = splitIntoSpeechChunks(
      "Your next class is Maths. It starts at 10 AM in Lab 3. Dr. Rao is teaching today. Bring your notebook.",
    );
    expect(chunks[0]).toBe("Your next class is Maths.");
    expect(chunks.length).toBeGreaterThan(1);
    expect(chunks.join(" ")).toBe(
      "Your next class is Maths. It starts at 10 AM in Lab 3. Dr. Rao is teaching today. Bring your notebook.",
    );
  });

  it("merges a tiny first sentence into the next", () => {
    expect(splitIntoSpeechChunks("Sure. Your next class is Maths at 10 AM.")[0]).toBe(
      "Sure. Your next class is Maths at 10 AM.",
    );
  });

  it("splits overlong sentences and never exceeds the limit", () => {
    const long = `Intro. ${Array.from({ length: 40 }, (_, i) => `item ${i}`).join(", ")}.`;
    for (const chunk of splitIntoSpeechChunks(long, 120))
      expect(chunk.length).toBeLessThanOrEqual(120);
  });

  it("returns nothing for empty text", () => {
    expect(splitIntoSpeechChunks("")).toEqual([]);
  });
});
