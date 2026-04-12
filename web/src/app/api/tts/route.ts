import { MsEdgeTTS, OUTPUT_FORMAT } from "msedge-tts";
import { buildTTSChunks } from "@/lib/tts-chunks";

const VOICE = "vi-VN-HoaiMyNeural";
const AUDIO_CACHE_TTL_MS = 1000 * 60 * 30;
const AUDIO_CACHE_MAX_ITEMS = 200;

const audioCache = new Map<string, { audio: Buffer; expiresAt: number }>();
const inflightAudio = new Map<string, Promise<Buffer>>();

export const dynamic = "force-dynamic";

function getCacheKey(text: string, rate: number) {
  return `${rate}:${text}`;
}

function getCachedAudio(cacheKey: string) {
  const cached = audioCache.get(cacheKey);
  if (!cached) return null;

  if (cached.expiresAt <= Date.now()) {
    audioCache.delete(cacheKey);
    return null;
  }

  return cached.audio;
}

function cacheAudio(cacheKey: string, audio: Buffer) {
  audioCache.set(cacheKey, {
    audio,
    expiresAt: Date.now() + AUDIO_CACHE_TTL_MS,
  });

  while (audioCache.size > AUDIO_CACHE_MAX_ITEMS) {
    const oldestKey = audioCache.keys().next().value;
    if (!oldestKey) break;
    audioCache.delete(oldestKey);
  }
}

async function synthesizeAudio(text: string, rate: number) {
  const cacheKey = getCacheKey(text, rate);

  let audio = getCachedAudio(cacheKey);
  if (audio) {
    return audio;
  }

  let inflightRequest = inflightAudio.get(cacheKey);
  if (!inflightRequest) {
    inflightRequest = (async () => {
      const tts = new MsEdgeTTS();

      try {
        await tts.setMetadata(VOICE, OUTPUT_FORMAT.AUDIO_24KHZ_96KBITRATE_MONO_MP3);

        const prosody = rate !== 1 ? { rate } : undefined;
        const { audioStream } = tts.toStream(text, prosody);

        const chunks: Buffer[] = [];
        for await (const chunk of audioStream) {
          chunks.push(Buffer.from(chunk));
        }

        const generatedAudio = Buffer.concat(chunks);
        cacheAudio(cacheKey, generatedAudio);
        return generatedAudio;
      } finally {
        tts.close();
        inflightAudio.delete(cacheKey);
      }
    })();

    inflightAudio.set(cacheKey, inflightRequest);
  }

  audio = await inflightRequest;
  return audio;
}

export async function POST(req: Request) {
  const { text, paragraphs, rate } = await req.json();

  const normalizedParagraphs =
    Array.isArray(paragraphs)
      ? paragraphs
          .filter((paragraph): paragraph is string => typeof paragraph === "string")
          .map((paragraph) => paragraph.trim())
          .filter(Boolean)
      : [];

  const normalizedText = typeof text === "string" ? text.trim() : "";

  if (!normalizedText && normalizedParagraphs.length === 0) {
    return new Response("Missing text", { status: 400 });
  }

  const normalizedRate = typeof rate === "number" ? rate : 1;
  const texts =
    normalizedParagraphs.length > 0
      ? buildTTSChunks(normalizedParagraphs).map((chunk) => chunk.text)
      : [normalizedText];

  const audioParts: Buffer[] = [];
  for (const chunkText of texts) {
    audioParts.push(await synthesizeAudio(chunkText, normalizedRate));
  }

  const audio = Buffer.concat(audioParts);

  return new Response(new Uint8Array(audio), {
    headers: {
      "Content-Type": "audio/mpeg",
      "Content-Length": String(audio.length),
      "Cache-Control": "private, max-age=1800",
    },
  });
}
