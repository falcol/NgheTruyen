import { describe, expect, it } from "vitest";
import {
  escapeXml,
  normalizeTtsVoice,
  validateTtsText,
} from "@/lib/tts-server";
import { DEFAULT_EDGE_VOICE } from "@/lib/tts-voices";

describe("tts-server helpers", () => {
  it("escapes SSML-sensitive characters", () => {
    expect(escapeXml(`A & B <C> "D" 'E'`)).toBe(
      "A &amp; B &lt;C&gt; &quot;D&quot; &apos;E&apos;",
    );
  });

  it("validates and trims text", () => {
    expect(validateTtsText("  xin   chào  ")).toBe("xin chào");
    expect(validateTtsText("")).toBeNull();
    expect(validateTtsText("   ")).toBeNull();
    expect(validateTtsText("x".repeat(801))).toBeNull();
    expect(validateTtsText("x".repeat(800))?.length).toBe(800);
  });

  it("normalizes voice ids", () => {
    expect(normalizeTtsVoice("vi-VN-NamMinhNeural")).toBe(
      "vi-VN-NamMinhNeural",
    );
    expect(normalizeTtsVoice("evil-voice")).toBe(DEFAULT_EDGE_VOICE);
    expect(normalizeTtsVoice(undefined)).toBe(DEFAULT_EDGE_VOICE);
  });
});
