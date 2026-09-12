import { MsEdgeTTS, OUTPUT_FORMAT } from "msedge-tts";
import { isValidEdgeVoice, DEFAULT_EDGE_VOICE } from "@/lib/tts-voices";

const MAX_TEXT_CHARS = 800;
const MAX_CACHE_ENTRIES = 96;
const MAX_CONCURRENT = 4;
const MAX_ATTEMPTS = 3;

/** Escape text for SSML (required by msedge-tts). */
export function escapeXml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

export function normalizeTtsVoice(voice: string | null | undefined): string {
  if (voice && isValidEdgeVoice(voice)) return voice;
  return DEFAULT_EDGE_VOICE;
}

export function validateTtsText(text: string): string | null {
  const trimmed = text.replace(/\s+/g, " ").trim();
  if (!trimmed) return null;
  if (trimmed.length > MAX_TEXT_CHARS) return null;
  return trimmed;
}

// Warm-instance cache (survives across requests on same Vercel isolate / dev process)
const audioCache = new Map<string, Buffer>();

function cacheGet(key: string): Buffer | undefined {
  const hit = audioCache.get(key);
  if (!hit) return undefined;
  // LRU bump
  audioCache.delete(key);
  audioCache.set(key, hit);
  return hit;
}

function cacheSet(key: string, value: Buffer) {
  if (audioCache.has(key)) audioCache.delete(key);
  audioCache.set(key, value);
  while (audioCache.size > MAX_CACHE_ENTRIES) {
    const oldest = audioCache.keys().next().value as string | undefined;
    if (oldest === undefined) break;
    audioCache.delete(oldest);
  }
}

// Limit concurrent Edge websocket sessions (parallel spam → empty audio)
let active = 0;
const waitQueue: Array<() => void> = [];

async function withSlot<T>(
  fn: () => Promise<T>,
  signal?: AbortSignal,
): Promise<T> {
  if (signal?.aborted) {
    throw new DOMException("Request aborted.", "AbortError");
  }
  if (active >= MAX_CONCURRENT) {
    // Wait for a slot, but bail out if the client disconnects while queued —
    // otherwise zombie requests hold queue positions for tens of seconds.
    await new Promise<void>((resolve, reject) => {
      const onAbort = () => reject(new DOMException("Request aborted.", "AbortError"));
      if (signal) {
        if (signal.aborted) return onAbort();
        signal.addEventListener("abort", onAbort, { once: true });
      }
      waitQueue.push(() => {
        signal?.removeEventListener("abort", onAbort);
        resolve();
      });
    });
  }
  if (signal?.aborted) {
    // Client is gone — pass the freed/unused slot to the next waiter.
    const next = waitQueue.shift();
    if (next) next();
    throw new DOMException("Request aborted.", "AbortError");
  }
  active += 1;
  try {
    return await fn();
  } finally {
    active -= 1;
    const next = waitQueue.shift();
    if (next) next();
  }
}

// ── Connection pool ─────────────────────────────────────────────────────────
// setMetadata() performs the WebSocket handshake — the dominant latency per
// chunk. Reuse idle connections per voice instead of dialing per request.
const idlePool = new Map<string, MsEdgeTTS[]>();
const POOL_MAX_PER_VOICE = 2;

async function acquireConn(voice: string): Promise<MsEdgeTTS> {
  const idle = idlePool.get(voice);
  const reused = idle?.pop();
  if (reused) return reused;
  const fresh = new MsEdgeTTS();
  await fresh.setMetadata(
    voice,
    OUTPUT_FORMAT.AUDIO_24KHZ_48KBITRATE_MONO_MP3,
  );
  return fresh;
}

function releaseConn(voice: string, conn: MsEdgeTTS, healthy: boolean) {
  if (!healthy) {
    try { conn.close(); } catch { /* already closed */ }
    return;
  }
  const idle = idlePool.get(voice) ?? [];
  if (idle.length >= POOL_MAX_PER_VOICE) {
    try { conn.close(); } catch { /* ignore */ }
    return;
  }
  idle.push(conn);
  idlePool.set(voice, idle);
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

async function synthesizeOnce(text: string, voiceName: string): Promise<Buffer> {
  const conn = await acquireConn(voiceName);
  let healthy = false;
  try {
    const { audioStream } = conn.toStream(escapeXml(text), { rate: 1 });

    const chunks: Buffer[] = [];
    for await (const chunk of audioStream) {
      chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
    }

    if (chunks.length === 0) {
      throw new Error("Empty TTS audio");
    }

    healthy = true;
    return Buffer.concat(chunks);
  } finally {
    releaseConn(voiceName, conn, healthy);
  }
}

// Deduplicate concurrent synthesis for the same text+voice — duplicate
// prefetches must not consume two Edge slots for identical work.
const inflightSynth = new Map<string, Promise<Buffer>>();

/**
 * Synthesize one chunk to an MP3 Buffer via Edge Read Aloud.
 * Rate is applied client-side (playbackRate) so server always uses rate 1
 * for better cache reuse and lower latency.
 */
export async function synthesizeMp3(
  text: string,
  voice: string,
  signal?: AbortSignal,
): Promise<Buffer> {
  const safe = validateTtsText(text);
  if (!safe) {
    throw new Error("Invalid TTS text");
  }
  if (signal?.aborted) {
    throw new DOMException("Request aborted.", "AbortError");
  }

  const voiceName = normalizeTtsVoice(voice);
  const key = `${voiceName}\0${safe}`;

  const cached = cacheGet(key);
  if (cached) return cached;

  const pending = inflightSynth.get(key);
  if (pending) return pending;

  const promise = (async () => {
    let lastErr: unknown;
    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
      if (signal?.aborted) {
        throw new DOMException("Request aborted.", "AbortError");
      }
      try {
        const audio = await withSlot(
          () => synthesizeOnce(safe, voiceName),
          signal,
        );
        cacheSet(key, audio);
        return audio;
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") throw err;
        lastErr = err;
        if (attempt < MAX_ATTEMPTS) {
          await sleep(150 * attempt);
        }
      }
    }
    throw lastErr instanceof Error
      ? lastErr
      : new Error("TTS synthesis failed");
  })().finally(() => {
    inflightSynth.delete(key);
  });

  inflightSynth.set(key, promise);
  return promise;
}
