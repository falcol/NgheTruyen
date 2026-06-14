export function getGradientFromString(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }

  // Anime-style gradient palettes — dark, saturated, cinematic
  const palettes = [
    ["from-rose-500/50",    "to-pink-900/60"],      // sakura
    ["from-violet-600/50",  "to-indigo-950/60"],    // twilight
    ["from-fuchsia-600/50", "to-purple-950/60"],    // amethyst
    ["from-red-600/50",     "to-rose-950/60"],      // crimson
    ["from-indigo-500/50",  "to-slate-900/60"],     // midnight
    ["from-pink-500/50",    "to-fuchsia-950/60"],   // neon sakura
    ["from-purple-600/50",  "to-violet-950/60"],    // deep violet
    ["from-sky-500/40",     "to-indigo-900/60"],    // moonlight
    ["from-orange-600/50",  "to-red-950/60"],       // ember
    ["from-teal-500/40",    "to-cyan-950/60"],      // jade
  ];

  const index = Math.abs(hash) % palettes.length;
  return `${palettes[index][0]} ${palettes[index][1]}`;
}
