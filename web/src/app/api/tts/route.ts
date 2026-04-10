import { MsEdgeTTS, OUTPUT_FORMAT } from "msedge-tts";

const VOICE = "vi-VN-HoaiMyNeural";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const { text, rate } = await req.json();

  if (!text || typeof text !== "string") {
    return new Response("Missing text", { status: 400 });
  }

  const tts = new MsEdgeTTS();
  await tts.setMetadata(VOICE, OUTPUT_FORMAT.AUDIO_24KHZ_96KBITRATE_MONO_MP3);

  const prosody = rate && rate !== 1 ? { rate: rate as number } : undefined;
  const { audioStream } = tts.toStream(text, prosody);

  const chunks: Buffer[] = [];
  for await (const chunk of audioStream) {
    chunks.push(Buffer.from(chunk));
  }
  tts.close();

  const audio = Buffer.concat(chunks);

  return new Response(audio, {
    headers: {
      "Content-Type": "audio/mpeg",
      "Content-Length": String(audio.length),
      "Cache-Control": "no-store",
    },
  });
}
