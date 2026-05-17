import { describe, expect, it } from "vitest";
import {
  parseStoredReaderSettings,
  themeToCssVars,
  getReaderTheme,
} from "@/lib/reader-settings";

describe("reader-settings", () => {
  it("parses stored settings with validation", () => {
    const s = parseStoredReaderSettings(
      JSON.stringify({ themeId: "night", fontId: "palatino", fontSizeId: "lg" }),
    );
    expect(s.themeId).toBe("night");
    expect(s.fontId).toBe("palatino");
    expect(s.fontSizeId).toBe("lg");
  });

  it("maps removed light themes to dark", () => {
    const s = parseStoredReaderSettings(
      JSON.stringify({ themeId: "sepia", fontId: "literata", fontSizeId: "md" }),
    );
    expect(s.themeId).toBe("warm-dark");
  });

  it("falls back on invalid ids", () => {
    const s = parseStoredReaderSettings(
      JSON.stringify({ themeId: "nope", fontId: "bad", fontSizeId: "x" }),
    );
    expect(s.themeId).toBe("dark");
    expect(s.fontId).toBe("literata");
    expect(s.fontSizeId).toBe("md");
  });

  it("themeToCssVars maps theme colors", () => {
    const vars = themeToCssVars(getReaderTheme("night"));
    expect(vars["--color-bg"]).toBe("#0a0e1a");
    expect(vars["--color-accent"]).toBe("#a78bfa");
  });
});
