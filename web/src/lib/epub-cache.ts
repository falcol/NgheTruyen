import crypto from "crypto";
import fs from "fs";
import path from "path";
import zlib from "zlib";
import type { EpubBookMeta, EpubChapter } from "./epub-types";

export const EPUB_META_CACHE_VERSION = 1;

export interface EpubMetaCachePayload {
  version: typeof EPUB_META_CACHE_VERSION;
  mtimeMs: number;
  size: number;
  meta: EpubBookMeta;
  spineIds: string[];
}

export interface EpubListSummary {
  filename: string;
  title: string;
  chapterCount: number | null;
}

export function bookCacheKey(filename: string): string {
  return crypto.createHash("sha256").update(filename).digest("hex").slice(0, 32);
}

export function getMetaCachePath(cacheDir: string, filename: string): string {
  return path.join(cacheDir, `${bookCacheKey(filename)}.json`);
}

function chapterCachePath(
  cacheDir: string,
  filename: string,
  chapterIdx: number,
): string {
  const idx = String(chapterIdx).padStart(5, "0");
  return path.join(cacheDir, bookCacheKey(filename), "ch", `${idx}.json`);
}

export function clearBookChapterCache(cacheDir: string, filename: string): void {
  const dir = path.join(cacheDir, bookCacheKey(filename), "ch");
  if (fs.existsSync(dir)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

function readJsonGz<T>(basePath: string): T | null {
  const gzPath = `${basePath}.gz`;
  try {
    if (fs.existsSync(gzPath)) {
      const text = zlib.gunzipSync(fs.readFileSync(gzPath)).toString("utf-8");
      return JSON.parse(text) as T;
    }
    if (fs.existsSync(basePath)) {
      return JSON.parse(fs.readFileSync(basePath, "utf-8")) as T;
    }
  } catch {
    return null;
  }
  return null;
}

export function readMetaCache(
  cacheDir: string,
  epubPath: string,
  filename: string,
): EpubMetaCachePayload | null {
  const cachePath = getMetaCachePath(cacheDir, filename);
  if (!fs.existsSync(cachePath) || !fs.existsSync(epubPath)) return null;

  let stat: fs.Stats;
  try {
    stat = fs.statSync(epubPath);
  } catch {
    return null;
  }

  try {
    const payload = JSON.parse(
      fs.readFileSync(cachePath, "utf-8"),
    ) as EpubMetaCachePayload;
    if (
      payload.version !== EPUB_META_CACHE_VERSION ||
      payload.mtimeMs !== stat.mtimeMs ||
      payload.size !== stat.size
    ) {
      return null;
    }
    return payload;
  } catch {
    return null;
  }
}

export function writeMetaCache(
  cacheDir: string,
  epubPath: string,
  filename: string,
  meta: EpubBookMeta,
  spineIds: string[],
): void {
  clearBookChapterCache(cacheDir, filename);
  const stat = fs.statSync(epubPath);
  const payload: EpubMetaCachePayload = {
    version: EPUB_META_CACHE_VERSION,
    mtimeMs: stat.mtimeMs,
    size: stat.size,
    meta,
    spineIds,
  };
  fs.mkdirSync(cacheDir, { recursive: true });
  fs.writeFileSync(getMetaCachePath(cacheDir, filename), JSON.stringify(payload));
}

export function hasChapterCache(
  cacheDir: string,
  filename: string,
  chapterIdx: number,
): boolean {
  const base = chapterCachePath(cacheDir, filename, chapterIdx);
  return fs.existsSync(`${base}.gz`) || fs.existsSync(base);
}

export function readChapterCache(
  cacheDir: string,
  filename: string,
  chapterIdx: number,
): EpubChapter | null {
  return readJsonGz<EpubChapter>(chapterCachePath(cacheDir, filename, chapterIdx));
}

export function writeChapterCache(
  cacheDir: string,
  filename: string,
  chapter: EpubChapter,
): void {
  const base = chapterCachePath(cacheDir, filename, chapter.index);
  fs.mkdirSync(path.dirname(base), { recursive: true });
  const json = JSON.stringify(chapter);
  fs.writeFileSync(`${base}.gz`, zlib.gzipSync(json));
}

export function listSummariesFromCache(
  epubDir: string,
  cacheDir: string,
  filenames: string[],
): EpubListSummary[] {
  return filenames.map((filename) => {
    const epubPath = path.join(epubDir, filename);
    const cached = readMetaCache(cacheDir, epubPath, filename);
    if (cached) {
      return {
        filename,
        title: cached.meta.title,
        chapterCount: cached.meta.chapters.length,
      };
    }
    return {
      filename,
      title: filename.replace(/\.epub$/i, ""),
      chapterCount: null,
    };
  });
}
