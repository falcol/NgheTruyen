import { describe, expect, it } from "vitest";
import {
  escapeXml,
  normalizeTtsVoice,
  validateTtsText,
} from "@/lib/tts-server";
import { DEFAULT_TTS_VOICE, getVoiceEngine } from "@/lib/tts-voices";

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

  it("normalizes voice ids across engines", () => {
    expect(normalizeTtsVoice("vi-VN-NamMinhNeural")).toBe(
      "vi-VN-NamMinhNeural",
    );
    expect(normalizeTtsVoice("gt-vi")).toBe("gt-vi");
    expect(normalizeTtsVoice("evil-voice")).toBe(DEFAULT_TTS_VOICE);
    expect(normalizeTtsVoice(undefined)).toBe(DEFAULT_TTS_VOICE);
  });

  it("maps voice ids to engines", () => {
    expect(getVoiceEngine("vi-VN-HoaiMyNeural")).toBe("edge");
    expect(getVoiceEngine("vi-VN-NamMinhNeural")).toBe("edge");
    expect(getVoiceEngine("gt-vi")).toBe("google");
    expect(getVoiceEngine("bogus")).toBeNull();
  });
});
