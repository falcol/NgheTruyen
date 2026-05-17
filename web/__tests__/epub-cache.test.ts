import fs from "fs";
import os from "os";
import path from "path";
import { afterEach, describe, expect, it } from "vitest";
import {
  listSummariesFromCache,
  readChapterCache,
  readMetaCache,
  writeChapterCache,
  writeMetaCache,
} from "@/lib/epub-cache";

describe("epub-cache", () => {
  let tmpDir: string;

  afterEach(() => {
    if (tmpDir && fs.existsSync(tmpDir)) {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  it("invalidates cache when epub file changes", () => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "epub-cache-"));
    const epubDir = path.join(tmpDir, "epub");
    const cacheDir = path.join(epubDir, ".cache");
    fs.mkdirSync(epubDir);

    const filename = "book.epub";
    const epubPath = path.join(epubDir, filename);
    fs.writeFileSync(epubPath, "v1");

    const meta = {
      filename,
      title: "Test Book",
      chapters: [{ index: 0, title: "Ch 1" }],
    };
    writeMetaCache(cacheDir, epubPath, filename, meta, ["spine-0"]);

    expect(readMetaCache(cacheDir, epubPath, filename)?.meta.title).toBe(
      "Test Book",
    );

    fs.writeFileSync(epubPath, "v2-updated");
    expect(readMetaCache(cacheDir, epubPath, filename)).toBeNull();
  });

  it("listSummariesFromCache reads cache without parsing epub", () => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "epub-cache-"));
    const epubDir = path.join(tmpDir, "epub");
    const cacheDir = path.join(epubDir, ".cache");
    fs.mkdirSync(epubDir);

    const filename = "cached.epub";
    const epubPath = path.join(epubDir, filename);
    fs.writeFileSync(epubPath, "content");

    writeMetaCache(
      cacheDir,
      epubPath,
      filename,
      {
        filename,
        title: "Cached Title",
        chapters: [
          { index: 0, title: "A" },
          { index: 1, title: "B" },
        ],
      },
      ["a", "b"],
    );

    const summaries = listSummariesFromCache(epubDir, cacheDir, [filename]);
    expect(summaries).toEqual([
      { filename, title: "Cached Title", chapterCount: 2 },
    ]);
  });

  it("writes and reads chapter cache", () => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "epub-ch-"));
    const cacheDir = path.join(tmpDir, ".cache");
    const filename = "book.epub";

    writeChapterCache(cacheDir, filename, {
      index: 2,
      title: "Ch 3",
      paragraphs: ["line one", "line two"],
    });

    const chapter = readChapterCache(cacheDir, filename, 2);
    expect(chapter?.title).toBe("Ch 3");
    expect(chapter?.paragraphs).toHaveLength(2);
  });
});
