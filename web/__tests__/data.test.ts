import { describe, it, expect } from "vitest";
import { makeDataDir } from "@/lib/data";

describe("data layer", () => {
  const data = makeDataDir("__tests__/fixtures");

  it("getChapterIndex returns array of chapter metadata", () => {
    const index = data.getChapterIndex("test-story");
    expect(index).toHaveLength(2);
    expect(index[0]).toEqual({ index: 0, title: "Chương 01: Test chapter one" });
    expect(index[1]).toEqual({ index: 1, title: "Chương 02: Test chapter two" });
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

  it("getTotalChapters returns correct count", () => {
    expect(data.getTotalChapters("test-story")).toBe(2);
  });

  it("listStories returns story directories", () => {
    const stories = data.listStories();
    expect(stories).toContain("test-story");
  });
});
