import { NextRequest, NextResponse } from "next/server";
import {
  normalizeTtsVoice,
  synthesizeMp3,
  validateTtsText,
} from "@/lib/tts-server";

export const runtime = "nodejs";
// Edge TTS websocket can need a few seconds on cold start
export const maxDuration = 30;

type TtsBody = {
  text?: unknown;
  voice?: unknown;
};

export async function POST(req: NextRequest) {
  let body: TtsBody;
  try {
    body = (await req.json()) as TtsBody;
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const text =
    typeof body.text === "string" ? validateTtsText(body.text) : null;
  if (!text) {
    return NextResponse.json(
      { error: "text is required (max 800 chars)" },
      { status: 400 },
    );
  }

  const voice = normalizeTtsVoice(
    typeof body.voice === "string" ? body.voice : undefined,
  );

  try {
    const audio = await synthesizeMp3(text, voice);

    // Immutable-ish: same text+voice → same bytes; browser/CDN can reuse
    const cacheKey = Buffer.from(`${voice}|${text}`).toString("base64url");

    return new NextResponse(new Uint8Array(audio), {
      status: 200,
      headers: {
        "Content-Type": "audio/mpeg",
        "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
        "X-TTS-Voice": voice,
        "X-TTS-Cache-Key": cacheKey,
      },
    });
  } catch (err) {
    console.error("[api/tts]", err);
    return NextResponse.json(
      { error: "TTS synthesis failed" },
      { status: 502 },
    );
  }
}
