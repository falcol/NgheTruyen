/**
 * Runtime EPUB access — reads pre-extracted cache only (no archive parsing).
 * Run `npm run epub:cache` after adding or updating .epub files.
 */
import fs from "fs";
import path from "path";
import {
  hasChapterCache,
  listSummariesFromCache,
  readChapterCache,
  readMetaCache,
  type EpubListSummary,
} from "./epub-cache";

export type {
  EpubChapter,
  EpubChapterMeta,
  EpubBookMeta,
} from "./epub-types";
export type { EpubListSummary } from "./epub-cache";

import type { EpubBookMeta, EpubChapter, EpubChapterMeta } from "./epub-types";

const EPUB_DIR = path.join(process.cwd(), "..", "epub");
const META_CACHE_DIR = path.join(EPUB_DIR, ".cache");

function epubPath(filename: string): string {
  return path.join(EPUB_DIR, filename);
}

export function listEpubFiles(): string[] {
  if (!fs.existsSync(EPUB_DIR)) return [];
  return fs.readdirSync(EPUB_DIR).filter((f) => f.endsWith(".epub"));
}

export function listEpubSummaries(): EpubListSummary[] {
  return listSummariesFromCache(EPUB_DIR, META_CACHE_DIR, listEpubFiles());
}

export function getEpubMeta(filename: string): EpubBookMeta | null {
  return readMetaCache(META_CACHE_DIR, epubPath(filename), filename)?.meta ?? null;
}

export function getEpubChapters(filename: string): EpubChapterMeta[] | null {
  return getEpubMeta(filename)?.chapters ?? null;
}

export function getEpubChapter(
  filename: string,
  chapterIdx: number,
): EpubChapter | null {
  if (!getEpubMeta(filename)) return null;
  return readChapterCache(META_CACHE_DIR, filename, chapterIdx);
}

export function isEpubChapterReady(
  filename: string,
  chapterIdx: number,
): boolean {
  if (!getEpubMeta(filename)) return false;
  return hasChapterCache(META_CACHE_DIR, filename, chapterIdx);
}
