import { describe, expect, it } from "vitest";
import {
  adjacentChapterContentUrls,
  adjacentChapterContentUrlsByIndex,
} from "@/lib/chapter-nav";
import type { VolumeRange } from "@/lib/data";

const vols: VolumeRange[] = [
  { url: "/data/slug/vol-001-ch001-050.json.gz", first: 1, last: 50 },
  { url: "/data/slug/vol-002-ch051-100.json.gz", first: 51, last: 100 },
];

describe("adjacentChapterContentUrls", () => {
  const chapters = [
    { index: 0, title: "A" },
    { index: 1, title: "B" },
    { index: 5, title: "F" },
  ];

  it("returns volume URLs for crawl stories", () => {
    const urls = adjacentChapterContentUrls("my-story", chapters, 1, vols);
    expect(urls.prev).toEqual({
      url: "/data/slug/vol-001-ch001-050.json.gz",
      chapterIdx: 0,
    });
    expect(urls.next).toEqual({
      url: "/data/slug/vol-001-ch001-050.json.gz",
      chapterIdx: 5,
    });
  });

  it("returns undefined neighbours without vols for crawl stories", () => {
    const urls = adjacentChapterContentUrls("my-story", chapters, 1);
    expect(urls.prev).toBeUndefined();
    expect(urls.next).toBeUndefined();
  });

  it("returns empty when the catalog holds only the open chapter", () => {
    // First-paint shape: readerFirstChapters serializes one entry, so the
    // catalog lookup cannot resolve neighbours until the index arrives.
    const urls = adjacentChapterContentUrls(
      "my-story",
      [{ index: 3 }],
      3,
      vols,
    );
    expect(urls).toEqual({});
  });

  it("returns epub-cache paths for epub slugs", () => {
    const urls = adjacentChapterContentUrls("epub-book.epub", chapters, 1);
    expect(urls.prev?.url).toMatch(/\/epub-cache\/.+\/ch\/00000\.json\.gz$/);
    expect(urls.prev?.chapterIdx).toBe(0);
    expect(urls.next?.url).toMatch(/\/epub-cache\/.+\/ch\/00005\.json\.gz$/);
    expect(urls.next?.chapterIdx).toBe(5);
  });
});

describe("adjacentChapterContentUrlsByIndex", () => {
  it("resolves neighbours from idx ± 1 without a catalog", () => {
    const urls = adjacentChapterContentUrlsByIndex("my-story", 3, 100, vols);
    expect(urls.prev).toEqual({
      url: "/data/slug/vol-001-ch001-050.json.gz",
      chapterIdx: 2,
    });
    expect(urls.next).toEqual({
      url: "/data/slug/vol-001-ch001-050.json.gz",
      chapterIdx: 4,
    });
  });

  it("crosses volume boundaries", () => {
    const urls = adjacentChapterContentUrlsByIndex("my-story", 50, 100, vols);
    expect(urls.prev?.url).toBe("/data/slug/vol-001-ch001-050.json.gz");
    expect(urls.next).toEqual({
      url: "/data/slug/vol-002-ch051-100.json.gz",
      chapterIdx: 51,
    });
  });

  it("respects story bounds", () => {
    expect(
      adjacentChapterContentUrlsByIndex("my-story", 0, 100, vols).prev,
    ).toBeUndefined();
    expect(
      adjacentChapterContentUrlsByIndex("my-story", 99, 100, vols).next,
    ).toBeUndefined();
  });

  it("resolves epub neighbours from idx ± 1", () => {
    const urls = adjacentChapterContentUrlsByIndex("epub-book.epub", 2, 10);
    expect(urls.prev?.url).toMatch(/\/epub-cache\/.+\/ch\/00001\.json\.gz$/);
    expect(urls.next?.url).toMatch(/\/epub-cache\/.+\/ch\/00003\.json\.gz$/);
  });
});
