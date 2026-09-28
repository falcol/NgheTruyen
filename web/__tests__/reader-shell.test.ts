import { describe, expect, it } from "vitest";
import { filterChapters } from "@/lib/chapter-list";
import {
  parseChapterIndex,
  readerFirstChapters,
} from "@/lib/reader-shell";

describe("reader first payload", () => {
  it("paints the open chapter without a title that exists only on another chapter", () => {
    const foreign = "Chương 88: SENTINEL_ONLY_THERE";
    const current = { index: 2, title: "Chương 3: Đang đọc" };
    const shell = readerFirstChapters(current);

    expect(JSON.stringify(shell)).not.toContain("SENTINEL_ONLY_THERE");
    expect(shell).toEqual([current]);

    const index = parseChapterIndex({
      meta: {
        chapters: [
          current,
          { index: 87, title: foreign, paragraphs: ["không được nằm trong payload đầu"] },
        ],
      },
    });
    expect(index.map((chapter) => chapter.title)).toContain(foreign);
    expect(filterChapters(index, "88").map((chapter) => chapter.title)).toEqual([foreign]);
    expect(filterChapters(index, "SENTINEL").map((chapter) => chapter.title)).toEqual([
      foreign,
    ]);
    expect(filterChapters(shell, "88")).toEqual([]);
  });
});
