/**
 * Runtime EPUB access — dual-mode, same pattern as lib/data.ts.
 *
 * Local mode (default, `npm run dev`): reads the pre-extracted meta cache
 * from public/epub-cache/. Run `npm run epub:cache` (or `prebuild`) to
 * generate it.
 *
 * External mode (Vercel, when NEXT_PUBLIC_EPUB_CACHE_URL is set): meta
 * (`index.json`, `<hash>.json`) is fetched as static assets from the
 * `epub-data` orphan branch, e.g.
 * https://raw.githubusercontent.com/<owner>/<repo>/epub-data
 * Chapter content was already CDN-static: clients fetch
 * /epub-cache/{hash}/ch/{idx}.json.gz via lib/epub-urls.ts.
 */
import path from "path";
import { fetchRemoteJson } from "./data-source";
import {
  EPUB_META_CACHE_VERSION,
  bookCacheKey,
  readCacheIndex,
  readMetaCache,
  type EpubCacheIndex,
  type EpubListSummary,
  type EpubMetaCachePayload,
} from "./epub-cache";

export type {
  EpubChapter,
  EpubChapterMeta,
  EpubBookMeta,
} from "./epub-types";
export type { EpubListSummary } from "./epub-cache";
// Base-aware version (respects NEXT_PUBLIC_EPUB_CACHE_URL). Local mode output
// is identical to the old lib/epub-cache.ts re-export.
export { chapterCacheUrlPath } from "./epub-urls";

import type { EpubBookMeta } from "./epub-types";

const META_CACHE_DIR = path.join(
  /* turbopackIgnore: true */ process.cwd(),
  "public",
  "epub-cache",
);

export function getEpubCacheBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_EPUB_CACHE_URL ?? "").replace(/\/$/, "");
}

export function isExternalEpubMode(): boolean {
  return getEpubCacheBaseUrl().length > 0;
}

export async function listEpubSummaries(): Promise<EpubListSummary[]> {
  if (isExternalEpubMode()) {
    const index = await fetchRemoteJson<EpubCacheIndex>(
      `${getEpubCacheBaseUrl()}/epub-cache/index.json`,
    );
    return index?.books ?? [];
  }
  return readCacheIndex(META_CACHE_DIR)?.books ?? [];
}

export async function getEpubMeta(
  filename: string,
): Promise<EpubBookMeta | null> {
  if (isExternalEpubMode()) {
    // Hashed lookup, same as the local cache path — no path traversal risk.
    const payload = await fetchRemoteJson<EpubMetaCachePayload>(
      `${getEpubCacheBaseUrl()}/epub-cache/${bookCacheKey(filename)}.json`,
    );
    if (!payload || payload.version !== EPUB_META_CACHE_VERSION) return null;
    return payload.meta;
  }
  return readMetaCache(META_CACHE_DIR, filename)?.meta ?? null;
}
