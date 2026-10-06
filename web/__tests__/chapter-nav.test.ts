import { describe, expect, it } from "vitest";
import { adjacentChapterContentUrls } from "@/lib/chapter-nav";

describe("adjacentChapterContentUrls", () => {
  const chapters = [
    { index: 0, title: "A" },
    { index: 1, title: "B" },
    { index: 5, title: "F" },
  ];

  it("returns API paths for crawl stories", () => {
    const urls = adjacentChapterContentUrls("my-story", chapters, 1);
    expect(urls.prev).toBe("/api/chapter/my-story/0");
    expect(urls.next).toBe("/api/chapter/my-story/5");
  });

  it("returns epub-cache paths for epub slugs", () => {
    const urls = adjacentChapterContentUrls("epub-book.epub", chapters, 1);
    expect(urls.prev).toMatch(/\/epub-cache\/.+\/ch\/00000\.json\.gz$/);
    expect(urls.next).toMatch(/\/epub-cache\/.+\/ch\/00005\.json\.gz$/);
  });
});
