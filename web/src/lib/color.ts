export function getGradientFromString(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }

  // Predefined gorgeous gradient palettes for deep dark mode
  const palettes = [
    ["from-blue-600/40", "to-purple-900/40"],
    ["from-emerald-600/40", "to-teal-900/40"],
    ["from-rose-600/40", "to-orange-900/40"],
    ["from-indigo-600/40", "to-cyan-900/40"],
    ["from-fuchsia-600/40", "to-pink-900/40"],
    ["from-amber-600/40", "to-red-900/40"],
    ["from-violet-600/40", "to-indigo-900/40"],
  ];

  const index = Math.abs(hash) % palettes.length;
  return `${palettes[index][0]} ${palettes[index][1]}`;
}
