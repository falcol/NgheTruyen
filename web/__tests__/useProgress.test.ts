import { describe, expect, it } from "vitest";
import {
  getChapterScrollY,
  parseProgress,
} from "@/hooks/useProgress";

describe("useProgress", () => {
  it("parses per-chapter scroll map", () => {
    const p = parseProgress({
      chapterIdx: 3,
      scrollByChapter: { "3": 1200, "5": 400 },
      timestamp: 1,
    });
    expect(p?.chapterIdx).toBe(3);
    expect(getChapterScrollY(p, 3)).toBe(1200);
    expect(getChapterScrollY(p, 5)).toBe(400);
    expect(getChapterScrollY(p, 0)).toBe(0);
  });

  it("migrates legacy scrollY field", () => {
    const p = parseProgress({ chapterIdx: 7, scrollY: 900 });
    expect(getChapterScrollY(p, 7)).toBe(900);
  });
});
