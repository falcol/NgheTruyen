import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  applyReaderThemeToDocument,
  getReaderFont,
  getReaderTheme,
  parseStoredReaderSettings,
  READER_FONTS,
  READER_THEMES,
  shouldUseChapterMotion,
  themeToCssVars,
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

  it("keeps dark presets, document theme, and Palatino", () => {
    expect(READER_THEMES.map((theme) => theme.id)).not.toEqual(
      expect.arrayContaining(["light", "sepia", "paper"]),
    );
    for (const theme of READER_THEMES) {
      expect(theme.id).not.toMatch(/light|sepia|paper/);
      expect(theme.name).not.toMatch(/light|sepia|paper|charcoal|amoled/i);
    }
    expect(getReaderTheme("light").id).toBe("dark");
    expect(getReaderTheme("sepia").id).toBe("warm-dark");
    expect(getReaderFont("palatino").name).toBe("Palatino");
    expect(READER_FONTS.some((font) => font.id === "palatino")).toBe(true);

    const restore = applyReaderThemeToDocument(
      getReaderTheme("night"),
      getReaderFont("palatino").family,
      1.125,
    );
    expect(document.documentElement.style.getPropertyValue("--color-bg")).toBe("#0a0e1a");
    expect(document.documentElement.style.getPropertyValue("--reader-font-family")).toContain(
      "Palatino",
    );
    restore();
  });

  it("honors prefers-reduced-motion in the stylesheet and the motion helper", () => {
    const css = readFileSync(
      path.resolve(__dirname, "../src/app/globals.css"),
      "utf8",
    );
    expect(css).toContain("prefers-reduced-motion: reduce");
    expect(css).toContain("#06070f");
    expect(css).toContain("#e879a0");

    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: query.includes("prefers-reduced-motion"),
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
      onchange: null,
    })) as typeof window.matchMedia;
    expect(shouldUseChapterMotion()).toBe(false);
    window.matchMedia = original;
  });
});
