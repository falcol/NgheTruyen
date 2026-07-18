import { MsEdgeTTS, OUTPUT_FORMAT } from "msedge-tts";
import { isValidEdgeVoice, DEFAULT_EDGE_VOICE } from "@/lib/tts-voices";

const MAX_TEXT_CHARS = 800;
const MAX_CACHE_ENTRIES = 96;
const MAX_CONCURRENT = 3;
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

async function withSlot<T>(fn: () => Promise<T>): Promise<T> {
  if (active >= MAX_CONCURRENT) {
    await new Promise<void>((resolve) => waitQueue.push(resolve));
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

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

async function synthesizeOnce(text: string, voiceName: string): Promise<Buffer> {
  const tts = new MsEdgeTTS();
  try {
    await tts.setMetadata(
      voiceName,
      OUTPUT_FORMAT.AUDIO_24KHZ_48KBITRATE_MONO_MP3,
    );

    const { audioStream } = tts.toStream(escapeXml(text), { rate: 1 });

    const chunks: Buffer[] = [];
    for await (const chunk of audioStream) {
      chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
    }

    if (chunks.length === 0) {
      throw new Error("Empty TTS audio");
    }

    return Buffer.concat(chunks);
  } finally {
    tts.close();
  }
}

/**
 * Synthesize one chunk to an MP3 Buffer via Edge Read Aloud.
 * Rate is applied client-side (playbackRate) so server always uses rate 1
 * for better cache reuse and lower latency.
 */
export async function synthesizeMp3(
  text: string,
  voice: string,
): Promise<Buffer> {
  const safe = validateTtsText(text);
  if (!safe) {
    throw new Error("Invalid TTS text");
  }

  const voiceName = normalizeTtsVoice(voice);
  const key = `${voiceName}\0${safe}`;

  const cached = cacheGet(key);
  if (cached) return cached;

  let lastErr: unknown;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    try {
      const audio = await withSlot(() => synthesizeOnce(safe, voiceName));
      cacheSet(key, audio);
      return audio;
    } catch (err) {
      lastErr = err;
      if (attempt < MAX_ATTEMPTS) {
        await sleep(150 * attempt);
      }
    }
  }

  throw lastErr instanceof Error
    ? lastErr
    : new Error("TTS synthesis failed");
}
