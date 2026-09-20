import { describe, expect, it } from "vitest";
import {
  CHAPTER_LIST_PAGE,
  filterChapters,
  visibleChapterWindow,
  windowRangeForJump,
} from "@/lib/chapter-list";

const chapters = Array.from({ length: 200 }, (_, i) => ({
  index: i,
  title: `Chương ${i + 1}: tiêu đề`,
}));

describe("filterChapters", () => {
  it("keeps every Chương title when the query is chương", () => {
    expect(filterChapters(chapters, "chương")).toHaveLength(200);
  });

  it("matches a printed chapter number", () => {
    expect(filterChapters(chapters, "200").map((ch) => ch.index)).toEqual([199]);
  });

  it("ignores list index when the title number differs", () => {
    const mixed = [
      { index: 1011, title: "Chương 997: vũ nhục heo" },
      { index: 1026, title: "Chương 1012: tai bay vạ gió" },
    ];
    expect(filterChapters(mixed, "1012").map((ch) => ch.index)).toEqual([1026]);
  });

  it("matches a numeric query to the Chương number only", () => {
    expect(filterChapters(chapters, "10").map((ch) => ch.index)).toEqual([9]);
  });

  it("treats padded Chương 01 as chapter 1", () => {
    const padded = [{ index: 0, title: "Chương 01: mở đầu" }];
    expect(filterChapters(padded, "1").map((ch) => ch.index)).toEqual([0]);
  });
});

describe("visibleChapterWindow", () => {
  it("does not mount the full catalog when many titles still match", () => {
    const filtered = filterChapters(chapters, "c");
    const { items, hasMoreAfter } = visibleChapterWindow(
      filtered,
      0,
      CHAPTER_LIST_PAGE,
    );
    expect(filtered.length).toBe(200);
    expect(items).toHaveLength(CHAPTER_LIST_PAGE);
    expect(hasMoreAfter).toBe(true);
  });
});

describe("windowRangeForJump", () => {
  it("keeps the jump window bounded instead of mounting 0..current", () => {
    const { start, count } = windowRangeForJump(chapters, 150);
    const { items } = visibleChapterWindow(chapters, start, count);
    expect(items.length).toBeLessThanOrEqual(CHAPTER_LIST_PAGE);
    expect(items.some((ch) => ch.index === 150)).toBe(true);
  });
});
