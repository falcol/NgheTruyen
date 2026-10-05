import type { ChapterPayload } from "./chapter-prefetch";
import {
  readDurableChapter,
  rememberDurableChapter,
} from "./chapter-prefetch";

/**
 * Chapter bodies for crawler-fed stories live in static volume .json.gz files
 * (about 50 chapters, ~150KB each) served from /data by the CDN. This loader
 * fetches a whole volume once, keeps a few parsed volumes in RAM, and extracts
 * single chapters client-side — no serverless fs access involved.
 */

interface Volume {
  chapters: ChapterPayload[];
}

// Parsed volumes are heavy (~50 chapters of text); keep only a handful.
const volCache = new Map<string, Volume>();
const volInflight = new Map<string, Promise<Volume>>();
const MAX_VOL_CACHE = 4;

function evictOldestVolume() {
  if (volCache.size <= MAX_VOL_CACHE) return;
  const first = volCache.keys().next().value;
  if (first) volCache.delete(first);
}

/** Cache key for one chapter inside a volume. Distinct from the vol URL so
 *  chapters of the same volume never collide in the durable store. */
export function volChapterKey(volUrl: string, chapterIdx: number): string {
  return `${volUrl}#ch=${chapterIdx}`;
}

async function fetchVolume(volUrl: string): Promise<Volume> {
  const res = await fetch(volUrl);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  if (!res.body) throw new Error("Empty response body");
  const decompressed = res.body.pipeThrough(new DecompressionStream("gzip"));
  const text = await new Response(decompressed).text();
  return JSON.parse(text) as Volume;
}

/** Shared volume fetch, deduped across concurrent chapter loads/prefetches. */
function volumeShared(volUrl: string): Promise<Volume> {
  const hit = volCache.get(volUrl);
  if (hit) return Promise.resolve(hit);

  const pending = volInflight.get(volUrl);
  if (pending) return pending;

  const promise = fetchVolume(volUrl)
    .then((vol) => {
      volCache.set(volUrl, vol);
      evictOldestVolume();
      return vol;
    })
    .finally(() => {
      volInflight.delete(volUrl);
    });

  volInflight.set(volUrl, promise);
  return promise;
}

function findChapter(vol: Volume, chapterIdx: number): ChapterPayload | null {
  return vol.chapters.find((c) => c.index === chapterIdx) ?? null;
}

/** Synchronous peek: durable chapter cache first, then a cached volume. */
export function peekVolChapter(
  volUrl: string,
  chapterIdx: number,
): ChapterPayload | undefined {
  const durable = readDurableChapter(volChapterKey(volUrl, chapterIdx));
  if (durable) return durable;
  const vol = volCache.get(volUrl);
  const chapter = vol ? findChapter(vol, chapterIdx) : null;
  return chapter ?? undefined;
}

/** Prefetch a chapter: warms the volume (or the durable cache) without throwing. */
export function prefetchVolChapter(
  volUrl: string,
  chapterIdx: number,
): Promise<ChapterPayload> {
  const key = volChapterKey(volUrl, chapterIdx);
  const hit = peekVolChapter(volUrl, chapterIdx);
  if (hit) return Promise.resolve(hit);

  return volumeShared(volUrl).then((vol) => {
    const chapter = findChapter(vol, chapterIdx);
    if (!chapter) throw new Error(`Chapter ${chapterIdx} not in volume`);
    rememberDurableChapter(key, chapter);
    return chapter;
  });
}

/**
 * Wait for a chapter inside its volume. The caller's `signal` only cancels THIS
 * wait (same contract as chapter-prefetch loadChapterContent): the underlying
 * volume fetch keeps running and still populates the cache for other readers.
 */
export function loadVolChapter(
  volUrl: string,
  chapterIdx: number,
  signal: AbortSignal,
): Promise<ChapterPayload> {
  const hit = peekVolChapter(volUrl, chapterIdx);
  if (hit) return Promise.resolve(hit);

  const key = volChapterKey(volUrl, chapterIdx);
  const shared = volumeShared(volUrl).then((vol) => {
    const chapter = findChapter(vol, chapterIdx);
    if (!chapter) throw new Error(`Chapter ${chapterIdx} not in volume`);
    rememberDurableChapter(key, chapter);
    return chapter;
  });

  if (signal.aborted) {
    return Promise.reject(
      new DOMException("The operation was aborted.", "AbortError"),
    );
  }

  return new Promise<ChapterPayload>((resolve, reject) => {
    const onAbort = () =>
      reject(new DOMException("The operation was aborted.", "AbortError"));
    signal.addEventListener("abort", onAbort, { once: true });
    shared.then(
      (payload) => {
        signal.removeEventListener("abort", onAbort);
        resolve(payload);
      },
      (err: unknown) => {
        signal.removeEventListener("abort", onAbort);
        reject(err);
      },
    );
  });
}
