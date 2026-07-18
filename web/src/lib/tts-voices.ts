/** Fixed Vietnamese neural voices from Microsoft Edge TTS (server-side). */

export interface EdgeTTSVoice {
  /** ShortName sent to /api/tts (e.g. vi-VN-HoaiMyNeural) */
  name: string;
  label: string;
  gender: "Female" | "Male";
}

export const EDGE_VI_VOICES: EdgeTTSVoice[] = [
  {
    name: "vi-VN-HoaiMyNeural",
    label: "Hoài My (Nữ)",
    gender: "Female",
  },
  {
    name: "vi-VN-NamMinhNeural",
    label: "Nam Minh (Nam)",
    gender: "Male",
  },
];

export const DEFAULT_EDGE_VOICE = EDGE_VI_VOICES[0].name;

export function isValidEdgeVoice(name: string): boolean {
  return EDGE_VI_VOICES.some((v) => v.name === name);
}
