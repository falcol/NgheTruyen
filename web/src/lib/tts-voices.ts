/**
 * Voice registry for /api/tts.
 * Two engines:
 * - "edge":   Microsoft Edge neural voices (msedge-tts websocket proxy)
 * - "google": Google Translate TTS (translate_tts) — the free voice the
 *             Read Aloud extension's "Google Translate" engine uses
 */

export type TtsEngine = "edge" | "google";

export interface TTSVoice {
  /** Voice id sent to /api/tts (e.g. vi-VN-HoaiMyNeural, gt-vi) */
  name: string;
  label: string;
  gender: "Female" | "Male";
  engine: TtsEngine;
}

/** Fixed Vietnamese neural voices from Microsoft Edge TTS. */
export const EDGE_VI_VOICES: TTSVoice[] = [
  {
    name: "vi-VN-HoaiMyNeural",
    label: "Hoài My (Nữ)",
    gender: "Female",
    engine: "edge",
  },
  {
    name: "vi-VN-NamMinhNeural",
    label: "Nam Minh (Nam)",
    gender: "Male",
    engine: "edge",
  },
];

/**
 * Free Google Translate voice for Vietnamese (translate_tts, client=tw-ob).
 * Google exposes a single voice per language — the same one Read Aloud's
 * "Google Translate" engine plays. Quality is below Edge neural, but there is
 * no websocket handshake cost and it does not depend on msedge-tts.
 */
export const GOOGLE_VI_VOICES: TTSVoice[] = [
  {
    name: "gt-vi",
    label: "Google (Nữ · Free)",
    gender: "Female",
    engine: "google",
  },
];

/** All selectable voices, in picker order. */
export const TTS_VOICES: TTSVoice[] = [...EDGE_VI_VOICES, ...GOOGLE_VI_VOICES];

export const DEFAULT_TTS_VOICE = TTS_VOICES[0].name;

export function getVoice(name: string): TTSVoice | undefined {
  return TTS_VOICES.find((v) => v.name === name);
}

export function isValidTtsVoice(name: string): boolean {
  return getVoice(name) !== undefined;
}

export function getVoiceEngine(name: string): TtsEngine | null {
  return getVoice(name)?.engine ?? null;
}

