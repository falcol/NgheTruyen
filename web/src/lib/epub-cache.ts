import crypto from "crypto";
import fs from "fs";
import path from "path";
import zlib from "zlib";
import type { EpubBookMeta, EpubChapter } from "./epub-types";

export const EPUB_META_CACHE_VERSION = 2;

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

export interface EpubCacheIndex {
  version: typeof EPUB_META_CACHE_VERSION;
  books: EpubListSummary[];
}

export function bookCacheKey(filename: string): string {
  return crypto.createHash("sha256").update(filename).digest("hex").slice(0, 32);
}

export function getMetaCachePath(cacheDir: string, filename: string): string {
  return path.join(cacheDir, `${bookCacheKey(filename)}.json`);
}

function chapterCacheFsPath(
  cacheDir: string,
  filename: string,
  chapterIdx: number,
): string {
  const idx = String(chapterIdx).padStart(5, "0");
  return path.join(cacheDir, bookCacheKey(filename), "ch", `${idx}.json.gz`);
}

export function chapterCacheUrlPath(filename: string, chapterIdx: number): string {
  const idx = String(chapterIdx).padStart(5, "0");
  return `/epub-cache/${bookCacheKey(filename)}/ch/${idx}.json.gz`;
}

export function clearBookChapterCache(cacheDir: string, filename: string): void {
  const dir = path.join(cacheDir, bookCacheKey(filename), "ch");
  if (fs.existsSync(dir)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

// Runtime-safe read: no mtime check (Vercel may reset mtime on deploy copy).
// Returns whatever cache file is present; callers do not validate against epub source.
export function readMetaCache(
  cacheDir: string,
  filename: string,
): EpubMetaCachePayload | null {
  const cachePath = getMetaCachePath(cacheDir, filename);
  if (!fs.existsSync(cachePath)) return null;
  try {
    const payload = JSON.parse(
      fs.readFileSync(cachePath, "utf-8"),
    ) as EpubMetaCachePayload;
    if (payload.version !== EPUB_META_CACHE_VERSION) return null;
    return payload;
  } catch {
    return null;
  }
}

// Build-time only: check whether a loaded payload still matches the source epub.
// Never called at runtime — separates write-triggering logic from read paths.
export function isMetaCacheCurrent(
  payload: EpubMetaCachePayload | null,
  epubPath: string,
): boolean {
  if (!payload || !fs.existsSync(epubPath)) return false;
  try {
    const stat = fs.statSync(epubPath);
    return payload.mtimeMs === stat.mtimeMs && payload.size === stat.size;
  } catch {
    return false;
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
  return fs.existsSync(chapterCacheFsPath(cacheDir, filename, chapterIdx));
}

export function writeChapterCache(
  cacheDir: string,
  filename: string,
  chapter: EpubChapter,
): void {
  const target = chapterCacheFsPath(cacheDir, filename, chapter.index);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, zlib.gzipSync(JSON.stringify(chapter)));
}

const CACHE_INDEX_FILENAME = "index.json";

export function readCacheIndex(cacheDir: string): EpubCacheIndex | null {
  const indexPath = path.join(cacheDir, CACHE_INDEX_FILENAME);
  if (!fs.existsSync(indexPath)) return null;
  try {
    const payload = JSON.parse(fs.readFileSync(indexPath, "utf-8")) as EpubCacheIndex;
    if (payload.version !== EPUB_META_CACHE_VERSION) return null;
    return payload;
  } catch {
    return null;
  }
}

export function writeCacheIndex(
  cacheDir: string,
  books: EpubListSummary[],
): void {
  fs.mkdirSync(cacheDir, { recursive: true });
  const payload: EpubCacheIndex = { version: EPUB_META_CACHE_VERSION, books };
  fs.writeFileSync(
    path.join(cacheDir, CACHE_INDEX_FILENAME),
    JSON.stringify(payload),
  );
}
