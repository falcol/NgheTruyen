export interface ChapterPayload {
  index: number;
  title: string;
  paragraphs: string[];
}

const cache = new Map<string, ChapterPayload>();
const inflight = new Map<string, Promise<ChapterPayload>>();
const MAX_CACHE = 12;

function evictOldest() {
  if (cache.size <= MAX_CACHE) return;
  const first = cache.keys().next().value;
  if (first) cache.delete(first);
}

async function fetchPayload(url: string, signal?: AbortSignal): Promise<ChapterPayload> {
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);

  if (url.endsWith(".gz")) {
    if (!res.body) throw new Error("Empty response body");
    const decompressed = res.body.pipeThrough(new DecompressionStream("gzip"));
    const text = await new Response(decompressed).text();
    return JSON.parse(text) as ChapterPayload;
  }

  return res.json() as Promise<ChapterPayload>;
}

export function getCachedChapter(url: string): ChapterPayload | undefined {
  return cache.get(url);
}

/** Fetch and store in memory; dedupes concurrent requests for the same URL. */
export function prefetchChapterContent(url: string): Promise<ChapterPayload> {
  const hit = cache.get(url);
  if (hit) return Promise.resolve(hit);

  const pending = inflight.get(url);
  if (pending) return pending;

  const promise = fetchPayload(url)
    .then((payload) => {
      cache.set(url, payload);
      evictOldest();
      return payload;
    })
    .finally(() => {
      inflight.delete(url);
    });

  inflight.set(url, promise);
  return promise;
}

export async function loadChapterContent(
  url: string,
  signal: AbortSignal,
): Promise<ChapterPayload> {
  const hit = cache.get(url);
  if (hit) return hit;

  const pending = inflight.get(url);
  if (pending) return pending;

  const promise = fetchPayload(url, signal)
    .then((payload) => {
      cache.set(url, payload);
      evictOldest();
      return payload;
    })
    .finally(() => {
      inflight.delete(url);
    });

  inflight.set(url, promise);
  return promise;
}
