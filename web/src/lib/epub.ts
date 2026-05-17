/**
 * Runtime EPUB access — reads pre-extracted meta cache from public/epub-cache/.
 * Chapter content is fetched client-side from /epub-cache/{hash}/ch/{idx}.json.gz.
 * Run `npm run epub:cache` (or `prebuild`) to generate the cache.
 */
import path from "path";
import {
  chapterCacheUrlPath,
  readCacheIndex,
  readMetaCache,
  type EpubListSummary,
} from "./epub-cache";

export type {
  EpubChapter,
  EpubChapterMeta,
  EpubBookMeta,
} from "./epub-types";
export type { EpubListSummary } from "./epub-cache";
export { chapterCacheUrlPath } from "./epub-cache";

import type { EpubBookMeta } from "./epub-types";

const META_CACHE_DIR = path.join(process.cwd(), "public", "epub-cache");

export function listEpubSummaries(): EpubListSummary[] {
  return readCacheIndex(META_CACHE_DIR)?.books ?? [];
}

export function getEpubMeta(filename: string): EpubBookMeta | null {
  return readMetaCache(META_CACHE_DIR, filename)?.meta ?? null;
}
