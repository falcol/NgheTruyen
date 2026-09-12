import { describe, expect, it } from "vitest";
import {
  buildGoogleSegmentUrl,
  splitGoogleSegments,
} from "@/lib/tts-google";
import {
  DEFAULT_TTS_VOICE,
  GOOGLE_VI_VOICES,
  TTS_VOICES,
} from "@/lib/tts-voices";

const SEGMENT_CAP = 190; // translate_tts-safe cap used by splitGoogleSegments

describe("splitGoogleSegments", () => {
  it("returns short text as a single segment", () => {
    expect(splitGoogleSegments("Xin chào Việt Nam")).toEqual([
      "Xin chào Việt Nam",
    ]);
  });

  it("returns empty for blank text", () => {
    expect(splitGoogleSegments("   ")).toEqual([]);
    expect(splitGoogleSegments("")).toEqual([]);
  });

  it("splits long text at word boundaries within the char cap", () => {
    const words = Array.from({ length: 300 }, (_, i) => `từ${i}`);
    const text = words.join(" ");
    const segments = splitGoogleSegments(text);

    expect(segments.length).toBeGreaterThan(1);
    for (const seg of segments) {
      expect(seg.length).toBeLessThanOrEqual(SEGMENT_CAP);
      expect(seg.startsWith(" ")).toBe(false);
      expect(seg.endsWith(" ")).toBe(false);
      expect(seg.length).toBeGreaterThan(0);
    }
    // Rejoining (single-space) must reproduce the normalized source text
    expect(segments.join(" ")).toBe(text);
  });

  it("hard-splits a single token longer than the cap", () => {
    const token = "a".repeat(250);
    const segments = splitGoogleSegments(token);
    expect(segments.join("")).toBe(token);
    for (const seg of segments) {
      expect(seg.length).toBeLessThanOrEqual(SEGMENT_CAP);
    }
  });
});

describe("buildGoogleSegmentUrl", () => {
  it("targets translate_tts with Vietnamese tw-ob params", () => {
    const segment = "xin chào";
    const url = buildGoogleSegmentUrl(segment, 1, 3);

    expect(url.startsWith("https://translate.google.com/translate_tts?")).toBe(
      true,
    );
    const params = new URL(url).searchParams;
    expect(params.get("ie")).toBe("UTF-8");
    expect(params.get("q")).toBe(segment);
    expect(params.get("tl")).toBe("vi");
    expect(params.get("client")).toBe("tw-ob");
    expect(params.get("idx")).toBe("1");
    expect(params.get("total")).toBe("3");
    expect(params.get("textlen")).toBe(String(segment.length));
    expect(params.get("ttsspeed")).toBe("1");
  });
});

describe("voice registry", () => {
  it("includes the Google free voice alongside Edge voices", () => {
    expect(GOOGLE_VI_VOICES.map((v) => v.name)).toEqual(["gt-vi"]);
    expect(TTS_VOICES.some((v) => v.engine === "google")).toBe(true);
    expect(TTS_VOICES.some((v) => v.engine === "edge")).toBe(true);
    // Default stays the Edge neural voice (existing users keep their choice)
    expect(DEFAULT_TTS_VOICE).toBe("vi-VN-HoaiMyNeural");
  });
});
