export interface ReaderTheme {
  id: string;
  name: string;
  bg: string;
  surface: string;
  text: string;
  textMuted: string;
  accent: string;
  accentDim: string;
  border: string;
}

export interface ReaderFont {
  id: string;
  name: string;
  family: string;
}

export interface ReaderFontSize {
  id: string;
  name: string;
  rem: number;
}

export interface ReaderTextColor {
  id: string;
  name: string;
  value: string;
  valueMuted: string;
}

export const READER_SETTINGS_KEY = "reader-settings-v1";

export const DEFAULT_THEME_ID = "dark";
export const DEFAULT_FONT_ID = "literata";
export const DEFAULT_FONT_SIZE_ID = "md";
export const DEFAULT_TEXT_COLOR_ID = "default";

/** Dark themes only — tuned for long reading sessions. */
export const READER_THEMES: ReaderTheme[] = [
  {
    id: "dark",
    name: "Than",
    bg: "#0f0f0f",
    surface: "#1a1a1a",
    text: "#e8e8e8",
    textMuted: "#9ca3af",
    accent: "#60a5fa",
    accentDim: "#3b82f6",
    border: "#2d2d2d",
  },
  {
    id: "charcoal",
    name: "Charcoal",
    bg: "#141414",
    surface: "#222222",
    text: "#ececec",
    textMuted: "#a3a3a3",
    accent: "#38bdf8",
    accentDim: "#0ea5e9",
    border: "#333333",
  },
  {
    id: "forest",
    name: "Rừng",
    bg: "#0f1410",
    surface: "#1a221c",
    text: "#d8e4d8",
    textMuted: "#8fa88f",
    accent: "#6ee7b7",
    accentDim: "#34d399",
    border: "#2a352c",
  },
  {
    id: "night",
    name: "Đêm",
    bg: "#0a0e1a",
    surface: "#121829",
    text: "#dce4f5",
    textMuted: "#8b9cc0",
    accent: "#a78bfa",
    accentDim: "#8b5cf6",
    border: "#1e293b",
  },
  {
    id: "amoled",
    name: "AMOLED",
    bg: "#000000",
    surface: "#111111",
    text: "#f0f0f0",
    textMuted: "#888888",
    accent: "#22d3ee",
    accentDim: "#06b6d4",
    border: "#1f1f1f",
  },
  {
    id: "warm-dark",
    name: "Ấm tối",
    bg: "#1a1614",
    surface: "#252019",
    text: "#ede6dc",
    textMuted: "#a89888",
    accent: "#fbbf24",
    accentDim: "#d97706",
    border: "#3d342c",
  },
  {
    id: "ash",
    name: "Tro",
    bg: "#1a1a1a",
    surface: "#242424",
    text: "#a8a8a8",
    textMuted: "#737373",
    accent: "#6b7280",
    accentDim: "#4b5563",
    border: "#333333",
  },
];

export const READER_TEXT_COLORS: ReaderTextColor[] = [
  {
    id: "default",
    name: "Mặc định",
    value: "",
    valueMuted: "",
  },
  {
    id: "soft-white",
    name: "Trắng sữa",
    value: "#d1d5db",
    valueMuted: "#9ca3af",
  },
  {
    id: "gray",
    name: "Xám dịu",
    value: "#9ca3af",
    valueMuted: "#6b7280",
  },
  {
    id: "warm",
    name: "Vàng cát",
    value: "#d5c7b3",
    valueMuted: "#a39581",
  },
  {
    id: "green",
    name: "Lá nhạt",
    value: "#aabfaa",
    valueMuted: "#7a8f7a",
  },
  {
    id: "blue",
    name: "Xanh nhạt",
    value: "#b0c2d6",
    valueMuted: "#8092a6",
  },
];

export const READER_FONTS: ReaderFont[] = [
  {
    id: "palatino",
    name: "Palatino",
    family: '"Palatino Linotype", Palatino, "Book Antiqua", "Times New Roman", serif',
  },
  {
    id: "literata",
    name: "Literata",
    family: "var(--font-literata), Georgia, serif",
  },
  {
    id: "lora",
    name: "Lora",
    family: "var(--font-lora), Georgia, serif",
  },
  {
    id: "merriweather",
    name: "Merriweather",
    family: "var(--font-merriweather), Georgia, serif",
  },
  {
    id: "noto-serif",
    name: "Noto Serif",
    family: "var(--font-noto-serif), serif",
  },
  {
    id: "source-serif",
    name: "Source Serif 4",
    family: "var(--font-source-serif), Georgia, serif",
  },
  {
    id: "be-vietnam",
    name: "Be Vietnam Pro",
    family: "var(--font-be-vietnam), system-ui, sans-serif",
  },
];

export const READER_FONT_SIZES: ReaderFontSize[] = [
  { id: "sm", name: "Nhỏ", rem: 1 },
  { id: "md", name: "Vừa", rem: 1.125 },
  { id: "lg", name: "Lớn", rem: 1.25 },
  { id: "xl", name: "Rất lớn", rem: 1.375 },
];

const LEGACY_THEME_MAP: Record<string, string> = {
  light: "dark",
  sepia: "warm-dark",
  paper: "charcoal",
};

export function getReaderTheme(id: string): ReaderTheme {
  const mapped = LEGACY_THEME_MAP[id] ?? id;
  return READER_THEMES.find((t) => t.id === mapped) ?? READER_THEMES[0];
}

export function getReaderFont(id: string): ReaderFont {
  return READER_FONTS.find((f) => f.id === id) ?? READER_FONTS[0];
}

export function getReaderFontSize(id: string): ReaderFontSize {
  return READER_FONT_SIZES.find((s) => s.id === id) ?? READER_FONT_SIZES[1];
}

export function getReaderTextColor(id: string | undefined): ReaderTextColor {
  if (!id) return READER_TEXT_COLORS[0];
  return READER_TEXT_COLORS.find((c) => c.id === id) ?? READER_TEXT_COLORS[0];
}

export function themeToCssVars(
  theme: ReaderTheme,
  textColor?: ReaderTextColor,
): Record<string, string> {
  const text = textColor && textColor.value ? textColor.value : theme.text;
  const textMuted = textColor && textColor.valueMuted ? textColor.valueMuted : theme.textMuted;
  return {
    "--color-bg": theme.bg,
    "--color-surface": theme.surface,
    "--color-text": text,
    "--color-text-muted": textMuted,
    "--color-accent": theme.accent,
    "--color-accent-dim": theme.accentDim,
    "--color-border": theme.border,
  };
}

export interface StoredReaderSettings {
  themeId: string;
  fontId: string;
  fontSizeId: string;
  textColorId?: string;
}

export const DEFAULT_READER_SETTINGS: StoredReaderSettings = {
  themeId: DEFAULT_THEME_ID,
  fontId: DEFAULT_FONT_ID,
  fontSizeId: DEFAULT_FONT_SIZE_ID,
  textColorId: DEFAULT_TEXT_COLOR_ID,
};

export function parseStoredReaderSettings(raw: string | null): StoredReaderSettings {
  if (!raw) return DEFAULT_READER_SETTINGS;
  try {
    const o = JSON.parse(raw) as Partial<StoredReaderSettings>;
    const themeId = o.themeId
      ? getReaderTheme(o.themeId).id
      : DEFAULT_THEME_ID;
    return {
      themeId,
      fontId: READER_FONTS.some((f) => f.id === o.fontId) ? o.fontId! : DEFAULT_FONT_ID,
      fontSizeId: READER_FONT_SIZES.some((s) => s.id === o.fontSizeId)
        ? o.fontSizeId!
        : DEFAULT_FONT_SIZE_ID,
      textColorId: READER_TEXT_COLORS.some((c) => c.id === o.textColorId)
        ? o.textColorId!
        : DEFAULT_TEXT_COLOR_ID,
    };
  } catch {
    return DEFAULT_READER_SETTINGS;
  }
}

export function applyReaderThemeToDocument(
  theme: ReaderTheme,
  fontFamily: string,
  fontSizeRem: number,
  textColor?: ReaderTextColor,
): () => void {
  if (typeof document === "undefined") return () => {};

  const root = document.documentElement;
  const vars = themeToCssVars(theme, textColor);
  const previous: Record<string, string> = {};

  for (const [key, value] of Object.entries(vars)) {
    previous[key] = root.style.getPropertyValue(key);
    root.style.setProperty(key, value);
  }

  const prevFont = root.style.getPropertyValue("--reader-font-family");
  const prevSize = root.style.getPropertyValue("--reader-font-size");
  const prevBodyBg = document.body.style.backgroundColor;
  const prevBodyColor = document.body.style.color;

  root.style.setProperty("--reader-font-family", fontFamily);
  root.style.setProperty("--reader-font-size", `${fontSizeRem}rem`);
  document.body.style.backgroundColor = theme.bg;
  document.body.style.color = vars["--color-text"];

  return () => {
    for (const key of Object.keys(vars)) {
      if (previous[key]) root.style.setProperty(key, previous[key]);
      else root.style.removeProperty(key);
    }
    if (prevFont) root.style.setProperty("--reader-font-family", prevFont);
    else root.style.removeProperty("--reader-font-family");
    if (prevSize) root.style.setProperty("--reader-font-size", prevSize);
    else root.style.removeProperty("--reader-font-size");
    document.body.style.backgroundColor = prevBodyBg;
    document.body.style.color = prevBodyColor;
  };
}
