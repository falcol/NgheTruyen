import { describe, it, expect } from "vitest";
import { makeDataDir } from "@/lib/data";

describe("data layer", () => {
  const data = makeDataDir("__tests__/fixtures");

  it("getChapterIndex returns array of chapter metadata", () => {
    const index = data.getChapterIndex("test-story");
    expect(index).not.toBeNull();
    expect(index!).toHaveLength(2);
    expect(index![0]).toEqual({ index: 0, title: "Chương 01: Test chapter one" });
    expect(index![1]).toEqual({ index: 1, title: "Chương 02: Test chapter two" });
  });

  it("getChapterIndex returns null for non-existent slug", () => {
    expect(data.getChapterIndex("non-existent")).toBeNull();
  });

  it("getChapter returns chapter paragraphs from volume file", () => {
    const chapter = data.getChapter("test-story", 0);
    expect(chapter).not.toBeNull();
    expect(chapter!.title).toBe("Chương 01: Test chapter one");
    expect(chapter!.paragraphs).toHaveLength(2);
    expect(chapter!.paragraphs[0]).toBe("Đoạn văn thứ nhất.");
  });

  it("getChapter returns null for invalid index", () => {
    const chapter = data.getChapter("test-story", 99);
    expect(chapter).toBeNull();
  });

  it("getStoryMetadata returns story metadata", () => {
    expect(data.getStoryMetadata("test-story")).toEqual({
      story_title: "Test Story Title",
    });
  });

  it("getStoryTitle returns story title from metadata", () => {
    expect(data.getStoryTitle("test-story")).toBe("Test Story Title");
  });

  it("getTotalChapters returns correct count", () => {
    expect(data.getTotalChapters("test-story")).toBe(2);
  });

  it("listStories returns story directories", () => {
    const stories = data.listStories();
    expect(stories).toContain("test-story");
  });

  it("getVolumeManifest scans the directory without a prebuilt manifest", () => {
    expect(data.getVolumeManifest("test-story")).toEqual({
      indexUrl: "__tests__/fixtures/test-story/chapters_index.json.gz",
      vols: [
        {
          url: "__tests__/fixtures/test-story/vol-001-ch001-002.json",
          first: 1,
          last: 2,
        },
      ],
    });
  });

  it("getVolumeManifest prefers the prebuilt manifest file over the scan", () => {
    // Disk holds vol-009 (first:999); the file must win.
    expect(data.getVolumeManifest("manifest-story")).toEqual({
      indexUrl: "/data/fx/manifest-story/chapters_index.json.gz",
      vols: [
        {
          url: "/data/fx/manifest-story/vol-001-ch001-002.json",
          first: 1,
          last: 2,
        },
      ],
    });
  });

  it("getVolumeManifest falls back to the scan when the manifest is corrupt", () => {
    expect(data.getVolumeManifest("corrupt-manifest-story")).toEqual({
      indexUrl:
        "__tests__/fixtures/corrupt-manifest-story/chapters_index.json.gz",
      vols: [
        {
          url: "__tests__/fixtures/corrupt-manifest-story/vol-001-ch001-002.json",
          first: 1,
          last: 2,
        },
      ],
    });
  });

  it("getVolumeManifest returns null for non-existent slug", () => {
    expect(data.getVolumeManifest("non-existent")).toBeNull();
  });
});
