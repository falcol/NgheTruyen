export interface ChapterPayload {
  index: number;
  title: string;
  paragraphs: string[];
}

const cache = new Map<string, ChapterPayload>();
const inflight = new Map<string, Promise<ChapterPayload>>();
const MAX_CACHE = 12;

/** Bodies that must still be readable after the browser process exits. */
const DURABLE_PREFIX = "nt-chapter-v1:";
const DURABLE_ORDER_KEY = "nt-chapter-v1-order";
const MAX_DURABLE = 6;

export function durableChapterKey(url: string): string {
  return DURABLE_PREFIX + url;
}

function evictOldest() {
  if (cache.size <= MAX_CACHE) return;
  const first = cache.keys().next().value;
  if (first) cache.delete(first);
}

function browserStorage(): Storage | null {
  try {
    if (typeof localStorage === "undefined") return null;
    return localStorage;
  } catch {
    return null;
  }
}

function isChapterPayload(value: unknown): value is ChapterPayload {
  if (!value || typeof value !== "object") return false;
  const o = value as ChapterPayload;
  return (
    typeof o.index === "number" &&
    typeof o.title === "string" &&
    Array.isArray(o.paragraphs) &&
    o.paragraphs.every((p) => typeof p === "string")
  );
}

function readOrder(ls: Storage): string[] {
  try {
    const raw = ls.getItem(DURABLE_ORDER_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(parsed) ? parsed.filter((u) => typeof u === "string") : [];
  } catch {
    return [];
  }
}

/** Synchronous read. Corrupt or missing entries return null so the caller can hit the network. */
export function readDurableChapter(url: string): ChapterPayload | null {
  const ls = browserStorage();
  if (!ls) return null;
  const key = durableChapterKey(url);
  const raw = ls.getItem(key);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as { payload?: unknown };
    if (!isChapterPayload(parsed.payload)) {
      ls.removeItem(key);
      return null;
    }
    return parsed.payload;
  } catch {
    try {
      ls.removeItem(key);
    } catch {
      /* ignore quota / security errors */
    }
    return null;
  }
}

export function rememberDurableChapter(url: string, payload: ChapterPayload): void {
  const ls = browserStorage();
  if (!ls || !isChapterPayload(payload)) return;
  const order = [url, ...readOrder(ls).filter((u) => u !== url)];
  const keep = order.slice(0, MAX_DURABLE);
  for (const old of order.slice(MAX_DURABLE)) {
    ls.removeItem(durableChapterKey(old));
  }
  const record = JSON.stringify({ savedAt: Date.now(), payload });
  try {
    ls.setItem(durableChapterKey(url), record);
    ls.setItem(DURABLE_ORDER_KEY, JSON.stringify(keep));
  } catch {
    for (const old of keep.slice(1)) ls.removeItem(durableChapterKey(old));
    try {
      ls.setItem(durableChapterKey(url), record);
      ls.setItem(DURABLE_ORDER_KEY, JSON.stringify([url]));
    } catch {
      /* RAM cache still serves this session */
    }
  }
}

/** Drop the in-memory map. Durable localStorage entries stay (new document / new process). */
export function forgetChapterMemory(): void {
  cache.clear();
  inflight.clear();
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

/**
 * RAM first, then storage that survives process death.
 * A durable hit is copied into RAM so later readers skip storage and the network.
 */
export function getCachedChapter(url: string): ChapterPayload | undefined {
  const mem = cache.get(url);
  if (mem) return mem;
  const stored = readDurableChapter(url);
  if (!stored) return undefined;
  cache.set(url, stored);
  evictOldest();
  return stored;
}

/**
 * Start (or join) the shared in-flight fetch for `url`. The returned promise is
 * NOT bound to any single caller's AbortSignal: if one reader navigates away
 * mid-fetch, the network request keeps running so concurrent readers (and
 * prefetches) still resolve and the cache still gets populated for the next
 * visit. Dedupes concurrent requests for the same URL.
 */
function fetchShared(url: string): Promise<ChapterPayload> {
  const hit = getCachedChapter(url);
  if (hit) return Promise.resolve(hit);

  const pending = inflight.get(url);
  if (pending) return pending;

  const promise = fetchPayload(url)
    .then((payload) => {
      cache.set(url, payload);
      evictOldest();
      rememberDurableChapter(url, payload);
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
  const hit = getCachedChapter(url);
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
