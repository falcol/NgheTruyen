import { MsEdgeTTS, OUTPUT_FORMAT } from "msedge-tts";
import { synthesizeGoogleMp3 } from "@/lib/tts-google";
import {
  DEFAULT_TTS_VOICE,
  getVoiceEngine,
  isValidTtsVoice,
} from "@/lib/tts-voices";
import { createLimiter } from "@/lib/tts-limiter";

const MAX_TEXT_CHARS = 800;
const MAX_CACHE_ENTRIES = 96;
const MAX_CONCURRENT = 4;
const MAX_ATTEMPTS = 3;

/**
 * Google gets rate-limited/blocked hard from datacenter IPs. After repeated
 * failures, stop paying the retry cost: synthesize Google-voice chunks with
 * the Edge fallback voice until the cooldown expires — reading continuity
 * beats voice purity (header X-TTS-Voice still reports the requested voice).
 */
const GOOGLE_COOLDOWN_MS = 60_000;
let googleCooldownUntil = 0;


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
  if (voice && isValidTtsVoice(voice)) return voice;
  return DEFAULT_TTS_VOICE;
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

// Limit concurrent Edge websocket sessions (parallel spam → empty audio).
// Google requests share the same pattern but with their own (stricter) limit
// inside tts-google.ts, so one engine's bursts can't starve the other.
const withSlot = createLimiter(MAX_CONCURRENT);

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

/**
 * Synthesize one Google-voice chunk: Google Translate TTS first; on failure
 * fall back to the default Edge voice so a chapter never loses paragraphs
 * just because Google rate-limits the server IP (cooldown avoids paying the
 * retry cost on every chunk while Google is down).
 */
async function synthesizeGoogleChunk(
  text: string,
  signal?: AbortSignal,
): Promise<Buffer> {
  if (Date.now() < googleCooldownUntil) {
    return withSlot(() => synthesizeOnce(text, DEFAULT_TTS_VOICE), signal);
  }
  try {
    return await synthesizeGoogleMp3(text, signal);
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    googleCooldownUntil = Date.now() + GOOGLE_COOLDOWN_MS;
    console.warn(
      `[tts-server] Google TTS unavailable → Edge fallback for ${GOOGLE_COOLDOWN_MS}ms`,
      err,
    );
    return withSlot(() => synthesizeOnce(text, DEFAULT_TTS_VOICE), signal);
  }
}

// Deduplicate concurrent synthesis for the same text+voice — duplicate
// prefetches must not consume two Edge slots for identical work.
const inflightSynth = new Map<string, Promise<Buffer>>();

/**
 * Synthesize one chunk to an MP3 Buffer (Edge neural or Google Translate,
 * chosen by the voice id). Rate is applied client-side (playbackRate) so
 * server always uses rate 1 for better cache reuse and lower latency.
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
  const engine = getVoiceEngine(voiceName) ?? "edge";
  const key = `${voiceName}\0${safe}`;

  const cached = cacheGet(key);
  if (cached) return cached;

  const pending = inflightSynth.get(key);
  if (pending) return pending;

  const promise = (async () => {
    let lastErr: unknown;
    // Google already retries per segment internally — an extra outer loop
    // would triple worst-case latency; its failure path falls back to Edge.
    const attempts = engine === "google" ? 1 : MAX_ATTEMPTS;
    for (let attempt = 1; attempt <= attempts; attempt++) {
      if (signal?.aborted) {
        throw new DOMException("Request aborted.", "AbortError");
      }
      try {
        const audio =
          engine === "google"
            ? await synthesizeGoogleChunk(safe, signal)
            : await withSlot(() => synthesizeOnce(safe, voiceName), signal);
        cacheSet(key, audio);
        return audio;
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") throw err;
        lastErr = err;
        if (attempt < attempts) {
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
