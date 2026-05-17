"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  applyReaderThemeToDocument,
  DEFAULT_READER_SETTINGS,
  getReaderFont,
  getReaderFontSize,
  getReaderTheme,
  parseStoredReaderSettings,
  READER_SETTINGS_KEY,
  themeToCssVars,
  type StoredReaderSettings,
} from "@/lib/reader-settings";

function load(): StoredReaderSettings {
  if (typeof window === "undefined") return DEFAULT_READER_SETTINGS;
  return parseStoredReaderSettings(localStorage.getItem(READER_SETTINGS_KEY));
}

function save(next: StoredReaderSettings) {
  localStorage.setItem(READER_SETTINGS_KEY, JSON.stringify(next));
}

export function useReaderSettings() {
  const [settings, setSettings] = useState<StoredReaderSettings>(DEFAULT_READER_SETTINGS);

  useEffect(() => {
    setSettings(load());
  }, []);

  const update = useCallback((patch: Partial<StoredReaderSettings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      save(next);
      return next;
    });
  }, []);

  const setThemeId = useCallback((themeId: string) => update({ themeId }), [update]);
  const setFontId = useCallback((fontId: string) => update({ fontId }), [update]);
  const setFontSizeId = useCallback(
    (fontSizeId: string) => update({ fontSizeId }),
    [update],
  );

  const theme = useMemo(() => getReaderTheme(settings.themeId), [settings.themeId]);
  const font = useMemo(() => getReaderFont(settings.fontId), [settings.fontId]);
  const fontSize = useMemo(
    () => getReaderFontSize(settings.fontSizeId),
    [settings.fontSizeId],
  );

  const shellStyle = useMemo(
    () =>
      ({
        ...themeToCssVars(theme),
        "--reader-font-family": font.family,
        "--reader-font-size": `${fontSize.rem}rem`,
        backgroundColor: theme.bg,
        color: theme.text,
      }) as React.CSSProperties,
    [theme, font, fontSize],
  );

  useEffect(() => {
    return applyReaderThemeToDocument(theme, font.family, fontSize.rem);
  }, [theme, font.family, fontSize.rem]);

  useEffect(() => {
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", theme.bg);
  }, [theme.bg]);

  return {
    settings,
    theme,
    font,
    fontSize,
    shellStyle,
    setThemeId,
    setFontId,
    setFontSizeId,
  };
}
