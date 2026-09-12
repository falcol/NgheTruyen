/**
 * Google Translate TTS (translate_tts) — the free Vietnamese voice the
 * Read Aloud extension uses for its "Google Translate" engine.
 *
 * Endpoint: GET https://translate.google.com/translate_tts
 *   ?ie=UTF-8&q=<segment>&tl=vi&client=tw-ob&idx=<i>&total=<n>
 *   &textlen=<segment length>&ttsspeed=1
 *
 * Constraints of this unofficial API (must be treated gently):
 * - ≤200 chars per request → text is pre-split at word boundaries
 * - Strict per-IP rate limits (HTTP 429) → sequential segments with a small
 *   delay between requests, low global concurrency, long backoff on 429
 * - Requires a browser-like User-Agent (the bare Node UA gets rejected)
 */
import { createLimiter } from "@/lib/tts-limiter";

const GOOGLE_TTS_URL = "https://translate.google.com/translate_tts";
const GOOGLE_TTS_LANG = "vi";
/** translate_tts rejects >200 chars per request; stay comfortably below. */
const MAX_SEGMENT_CHARS = 190;
const SEGMENT_ATTEMPTS = 3;
/** Pause between segment requests (same IP) to dodge 429. */
const INTER_SEGMENT_DELAY_MS = 220;
/** Backoff between retries of one segment. */
const RETRY_BACKOFF_MS = 500;
/** Per-request cap so a hung Google connection can't eat the whole budget. */
const SEGMENT_TIMEOUT_MS = 8_000;
/** Google rate-limits bursts hard — keep global in-flight requests low. */
const GOOGLE_MAX_CONCURRENT = 2;

const withSlot = createLimiter(GOOGLE_MAX_CONCURRENT);

const REQUEST_HEADERS: Record<string, string> = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
  Referer: "https://translate.google.com/",
};

function abortError(): DOMException {
  return new DOMException("Request aborted.", "AbortError");
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) return Promise.reject(abortError());
  return new Promise((resolve, reject) => {
    const onAbort = () => {
      clearTimeout(timer);
      reject(abortError());
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/** Split text into ≤MAX_SEGMENT_CHARS pieces at word boundaries. */
export function splitGoogleSegments(text: string): string[] {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (!normalized) return [];
  if (normalized.length <= MAX_SEGMENT_CHARS) return [normalized];

  const segments: string[] = [];
  let remaining = normalized;
  while (remaining.length > MAX_SEGMENT_CHARS) {
    const windowText = remaining.slice(0, MAX_SEGMENT_CHARS + 1);
    const splitAt = windowText.lastIndexOf(" ");
    // Single token longer than the cap → hard split (degenerate input).
    const safeSplitAt = splitAt > 0 ? splitAt : MAX_SEGMENT_CHARS;
    segments.push(remaining.slice(0, safeSplitAt).trim());
    remaining = remaining.slice(safeSplitAt).trim();
  }
  if (remaining) segments.push(remaining);
  return segments;
}
/** Build a translate_tts URL for one segment (exported for tests). */
export function buildGoogleSegmentUrl(
  segment: string,
  idx: number,
  total: number,
): string {
  const params = new URLSearchParams({
    ie: "UTF-8",
    q: segment,
    tl: GOOGLE_TTS_LANG,
    client: "tw-ob",
    prev: "input",
    ttsspeed: "1",
    total: String(total),
    idx: String(idx),
    textlen: String(segment.length),
  });
  return `${GOOGLE_TTS_URL}?${params.toString()}`;
}

async function fetchSegmentBuffer(
  segment: string,
  idx: number,
  total: number,
  signal: AbortSignal | undefined,
): Promise<Buffer> {
  // Merge caller abort with a hard per-request timeout.
  const timeout = AbortSignal.timeout(SEGMENT_TIMEOUT_MS);
  const fetchSignal = signal ? AbortSignal.any([signal, timeout]) : timeout;

  const res = await fetch(buildGoogleSegmentUrl(segment, idx, total), {
    headers: REQUEST_HEADERS,
    signal: fetchSignal,
    // Next.js data cache must never serve a stale/HTML answer as audio
    cache: "no-store",
  });
  if (!res.ok) {
    void res.body?.cancel().catch(() => {});
    throw new Error(`Google TTS ${res.status}`);
  }
  const type = res.headers.get("content-type") ?? "";
  const buf = Buffer.from(await res.arrayBuffer());
  // Error pages / consent redirects are HTML; real audio is MP3 (audio/mpeg).
  if (!type.includes("audio") || buf.length < 256) {
    throw new Error(
      `Google TTS invalid response (${type || "unknown type"}, ${buf.length}B)`,
    );
  }
  return buf;
}

async function fetchSegmentWithRetry(
  segment: string,
  idx: number,
  total: number,
  signal: AbortSignal | undefined,
): Promise<Buffer> {
  let lastErr: unknown;
  for (let attempt = 1; attempt <= SEGMENT_ATTEMPTS; attempt++) {
    if (signal?.aborted) throw abortError();
    try {
      return await withSlot(
        () => fetchSegmentBuffer(segment, idx, total, signal),
        signal,
      );
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") throw err;
      lastErr = err;
      // 429 = rate limited → wait notably longer before hammering again.
      const rateLimited =
        lastErr instanceof Error && lastErr.message.includes("Google TTS 429");
      if (attempt < SEGMENT_ATTEMPTS) {
        await sleep(RETRY_BACKOFF_MS * attempt * (rateLimited ? 3 : 1), signal);
      }
    }
  }
  throw lastErr instanceof Error ? lastErr : new Error("Google TTS failed");
}

/**
 * Synthesize one chunk (≤800 chars) to a concatenated MP3 Buffer.
 * Segments are fetched sequentially — parallel bursts trip Google's rate
 * limit. MP3 frames concatenate cleanly (each part is self-contained).
 */
export async function synthesizeGoogleMp3(
  text: string,
  signal?: AbortSignal,
): Promise<Buffer> {
  const segments = splitGoogleSegments(text);
  if (segments.length === 0) throw new Error("Invalid TTS text");

  const buffers: Buffer[] = [];
  for (let i = 0; i < segments.length; i++) {
    if (signal?.aborted) throw abortError();
    if (i > 0) await sleep(INTER_SEGMENT_DELAY_MS, signal);
    buffers.push(
      await fetchSegmentWithRetry(segments[i], i, segments.length, signal),
    );
  }
  return Buffer.concat(buffers);
}

