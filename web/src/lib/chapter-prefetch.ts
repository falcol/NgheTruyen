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

/**
 * Start (or join) the shared in-flight fetch for `url`. The returned promise is
 * NOT bound to any single caller's AbortSignal: if one reader navigates away
 * mid-fetch, the network request keeps running so concurrent readers (and
 * prefetches) still resolve and the cache still gets populated for the next
 * visit. Dedupes concurrent requests for the same URL.
 */
function fetchShared(url: string): Promise<ChapterPayload> {
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

/** Fetch and store in memory; dedupes concurrent requests for the same URL. */
export function prefetchChapterContent(url: string): Promise<ChapterPayload> {
  return fetchShared(url);
}

/**
 * Wait for the shared fetch for `url`, resolving from cache if available.
 * The caller's `signal` only cancels THIS wait: if it aborts this promise
 * rejects with AbortError, but the underlying fetch keeps running (and populates
 * the cache) so other concurrent readers are unaffected. See fetchShared.
 */
export function loadChapterContent(
  url: string,
  signal: AbortSignal,
): Promise<ChapterPayload> {
  const hit = cache.get(url);
  if (hit) return Promise.resolve(hit);

  const shared = fetchShared(url);

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
