import zlib from "zlib";
import type { Chapter, ChapterMeta, StoryMetadata } from "./data";

// Dual-mode story data access for the crawl dataset.
//
// Local mode (default, `npm run dev`): data.ts reads ../public/data from disk,
// exactly as before. No network needed.
//
// External mode (Vercel, when NEXT_PUBLIC_DATA_URL is set): the dataset lives on
// the `story-data` orphan branch (same pattern as the epub-data branch) and is
// served over CDN, e.g. https://cdn.jsdelivr.net/gh/<owner>/<repo>@story-data.
// Files are fetched as static assets so serverless functions stay tiny instead
// of bundling ~200MB of vol-*.json.gz via outputFileTracingIncludes.
//
// Layout on the branch:
//   data/manifest.json
//   data/<source>/<slug>/chapters_index.json.gz
//   data/<source>/<slug>/metadata.json.gz
//   data/<source>/<slug>/vol-*.json.gz

export interface DataManifestEntry {
  slug: string;
  source: string;
  title: string;
  totalChapters: number;
  chapterCount: number;
  volFiles: string[];
}

export interface DataManifest {
  version: number;
  generatedAt: string;
  stories: DataManifestEntry[];
}

export const DATA_MANIFEST_VERSION = 1;

export function isSafeSlug(slug: string): boolean {
  return (
    !slug.includes("/") && !slug.includes("\\") && !slug.includes("..")
  );
}

export function getDataBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_DATA_URL ?? "").replace(/\/$/, "");
}

export function isExternalDataMode(): boolean {
  return getDataBaseUrl().length > 0;
}

// In-memory caches for fetched files. Published files are immutable per
// branch publish, so no mtime validation is needed (unlike local disk reads).
let manifestCache: DataManifest | null = null;
const indexCache = new Map<string, ChapterMeta[]>();
const metadataCache = new Map<string, StoryMetadata>();
const volumeCache = new Map<string, Chapter>();
const MAX_VOLUME_CACHE_SIZE = 200;

async function fetchBuffer(url: string): Promise<Buffer | null> {
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    return Buffer.from(await res.arrayBuffer());
  } catch {
    return null;
  }
}

// Fetch <logicalPath> preferring the .gz variant, falling back to plain JSON.
// Mirrors readJsonAny() in data.ts, but over HTTP. Shared by the crawl
// dataset (data.ts) and the EPUB meta cache (epub.ts).
export async function fetchRemoteJson<T>(logicalUrl: string): Promise<T | null> {
  const gzBuf = await fetchBuffer(logicalUrl + ".gz");
  if (gzBuf) {
    try {
      return JSON.parse(zlib.gunzipSync(gzBuf).toString("utf-8")) as T;
    } catch {
      /* corrupt gzip — fall through to plain variant */
    }
  }
  const buf = await fetchBuffer(logicalUrl);
  if (buf) {
    try {
      return JSON.parse(buf.toString("utf-8")) as T;
    } catch {
      return null;
    }
  }
  return null;
}

export async function loadDataManifest(): Promise<DataManifest | null> {
  if (manifestCache) return manifestCache;
  const base = getDataBaseUrl();
  if (!base) return null;
  const manifest = await fetchRemoteJson<DataManifest>(`${base}/data/manifest.json`);
  if (manifest && manifest.version === DATA_MANIFEST_VERSION) {
    manifestCache = manifest;
    return manifest;
  }
  return null;
}

export async function findManifestEntry(
  slug: string,
): Promise<DataManifestEntry | null> {
  if (!isSafeSlug(slug)) return null;
  const manifest = await loadDataManifest();
  return manifest?.stories.find((s) => s.slug === slug) ?? null;
}

function storyFileUrl(entry: DataManifestEntry, file: string): string {
  const base = getDataBaseUrl();
  return `${base}/data/${entry.source}/${encodeURIComponent(entry.slug)}/${file}`;
}

export async function remoteListStories(): Promise<string[]> {
  const manifest = await loadDataManifest();
  return manifest?.stories.map((s) => s.slug) ?? [];
}

export async function remoteListSummaries(): Promise<
  { slug: string; title: string; totalChapters: number }[]
> {
  const manifest = await loadDataManifest();
  return (
    manifest?.stories.map((s) => ({
      slug: s.slug,
      title: s.title,
      totalChapters: s.chapterCount,
    })) ?? []
  );
}

export async function remoteGetChapterIndex(
  slug: string,
): Promise<ChapterMeta[] | null> {
  const entry = await findManifestEntry(slug);
  if (!entry) return null;
  const key = `${entry.source}/${entry.slug}`;
  const cached = indexCache.get(key);
  if (cached) return cached;
  const data = await fetchRemoteJson<ChapterMeta[]>(
    storyFileUrl(entry, "chapters_index.json"),
  );
  if (data) indexCache.set(key, data);
  return data;
}

export async function remoteGetStoryMetadata(
  slug: string,
): Promise<StoryMetadata | null> {
  const entry = await findManifestEntry(slug);
  if (!entry) return null;
  const key = `${entry.source}/${entry.slug}`;
  const cached = metadataCache.get(key);
  if (cached) return cached;
  const data = await fetchRemoteJson<StoryMetadata>(
    storyFileUrl(entry, "metadata.json"),
  );
  if (data) metadataCache.set(key, data);
  return data;
}

export async function remoteGetStoryTitle(slug: string): Promise<string> {
  const entry = await findManifestEntry(slug);
  return entry?.title ?? slug;
}

export async function remoteGetTotalChapters(slug: string): Promise<number> {
  const index = await remoteGetChapterIndex(slug);
  if (!index || index.length === 0) return 0;
  // Max-based (not last-element-based) so an unsorted index can't shrink the total.
  return index.reduce((m, c) => Math.max(m, c.index), -1) + 1;
}

export async function remoteGetChapter(
  slug: string,
  chapterIdx: number,
): Promise<Chapter | null> {
  const cacheKey = `${slug}/${chapterIdx}`;
  const cached = volumeCache.get(cacheKey);
  if (cached) return cached;

  const entry = await findManifestEntry(slug);
  if (!entry) return null;
  const index = await remoteGetChapterIndex(slug);
  if (!index) return null;
  const position = index.findIndex((ch) => ch.index === chapterIdx);
  if (position === -1) return null;

  // Same volume math as local makeDataDir: 50 chapters per volume, ±2 neighbor search.
  const volNum = Math.floor(position / 50) + 1;
  for (let delta = 0; delta <= 2; delta++) {
    const candidates =
      delta === 0 ? [volNum] : [volNum + delta, volNum - delta];
    for (const tryVol of candidates) {
      if (tryVol < 1) continue;
      const prefix = `vol-${String(tryVol).padStart(3, "0")}-`;
      const volFile = entry.volFiles.find((f) => f.startsWith(prefix));
      if (!volFile) continue;
      const volData = await fetchRemoteJson<{ chapters: Chapter[] }>(
        storyFileUrl(entry, volFile.replace(/\.gz$/, "")),
      );
      const chapter = volData?.chapters.find((c) => c.index === chapterIdx);
      if (chapter) {
        if (volumeCache.size >= MAX_VOLUME_CACHE_SIZE) {
          const oldestKey = volumeCache.keys().next().value;
          if (oldestKey) volumeCache.delete(oldestKey);
        }
        volumeCache.set(cacheKey, chapter);
        return chapter;
      }
    }
  }
  return null;
}
