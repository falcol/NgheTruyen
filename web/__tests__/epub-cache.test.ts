import fs from "fs";
import os from "os";
import path from "path";
import zlib from "zlib";
import { afterEach, describe, expect, it } from "vitest";
import {
  isMetaCacheCurrent,
  readCacheIndex,
  readMetaCache,
  writeCacheIndex,
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

  it("readMetaCache returns payload without checking source epub", () => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "epub-cache-"));
    const epubDir = path.join(tmpDir, "epub");
    const cacheDir = path.join(tmpDir, "cache");
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

    expect(readMetaCache(cacheDir, filename)?.meta.title).toBe("Test Book");

    // Source epub modified but runtime read still succeeds — invalidation is
    // a separate concern (isMetaCacheCurrent), not a runtime concern.
    fs.writeFileSync(epubPath, "v2-updated");
    expect(readMetaCache(cacheDir, filename)?.meta.title).toBe("Test Book");
  });

  it("isMetaCacheCurrent detects source epub changes", () => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "epub-cache-"));
    const epubDir = path.join(tmpDir, "epub");
    const cacheDir = path.join(tmpDir, "cache");
    fs.mkdirSync(epubDir);

    const filename = "book.epub";
    const epubPath = path.join(epubDir, filename);
    fs.writeFileSync(epubPath, "v1");

    writeMetaCache(
      cacheDir,
      epubPath,
      filename,
      { filename, title: "T", chapters: [] },
      [],
    );

    const cached = readMetaCache(cacheDir, filename);
    expect(isMetaCacheCurrent(cached, epubPath)).toBe(true);

    fs.writeFileSync(epubPath, "v2-different-size");
    expect(isMetaCacheCurrent(cached, epubPath)).toBe(false);
  });

  it("cache index round-trip", () => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "epub-cache-"));
    const cacheDir = path.join(tmpDir, "cache");

    writeCacheIndex(cacheDir, [
      { filename: "a.epub", title: "A", chapterCount: 3 },
      { filename: "b.epub", title: "B", chapterCount: 5 },
    ]);

    const idx = readCacheIndex(cacheDir);
    expect(idx?.books).toHaveLength(2);
    expect(idx?.books[1].title).toBe("B");
  });

  it("writeChapterCache produces a gzipped JSON file", () => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "epub-ch-"));
    const cacheDir = path.join(tmpDir, "cache");
    const filename = "book.epub";

    writeChapterCache(cacheDir, filename, {
      index: 2,
      title: "Ch 3",
      paragraphs: ["line one", "line two"],
    });

    // Decompress manually to mirror what the browser will do via DecompressionStream.
    const written = fs.readdirSync(cacheDir, { recursive: true, withFileTypes: true })
      .filter((d) => d.isFile() && d.name.endsWith(".json.gz"))
      .map((d) => path.join(d.parentPath, d.name));
    expect(written).toHaveLength(1);

    const json = JSON.parse(
      zlib.gunzipSync(fs.readFileSync(written[0])).toString("utf-8"),
    );
    expect(json.title).toBe("Ch 3");
    expect(json.paragraphs).toHaveLength(2);
  });
});
