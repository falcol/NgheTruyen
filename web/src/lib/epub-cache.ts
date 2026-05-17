import crypto from "crypto";
import fs from "fs";
import path from "path";
import type { EpubBookMeta } from "./epub-types";

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

export function getMetaCachePath(cacheDir: string, filename: string): string {
  const key = crypto.createHash("sha256").update(filename).digest("hex").slice(0, 32);
  return path.join(cacheDir, `${key}.json`);
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
  const stat = fs.statSync(epubPath);
  const payload: EpubMetaCachePayload = {
    version: EPUB_META_CACHE_VERSION,
    mtimeMs: stat.mtimeMs,
    size: stat.size,
    meta,
    spineIds,
  };
  fs.mkdirSync(cacheDir, { recursive: true });
  const cachePath = getMetaCachePath(cacheDir, filename);
  fs.writeFileSync(cachePath, JSON.stringify(payload));
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
