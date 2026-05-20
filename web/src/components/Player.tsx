"use client";

import { useState } from "react";
import { useReaderSettingsContext } from "@/context/ReaderSettingsContext";
import {
  READER_FONTS,
  READER_FONT_SIZES,
  READER_THEMES,
  READER_TEXT_COLORS,
} from "@/lib/reader-settings";

const RATES = [0.75, 1, 1.25, 1.5, 2];

function Chip({
  active,
  onClick,
  children,
  className = "",
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-3 py-1.5 text-xs rounded-full transition-colors ${className} ${
        active
          ? "bg-[var(--color-accent)] text-black font-semibold"
          : "bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:opacity-90 ring-1 ring-[var(--color-border)]"
      }`}
    >
      {children}
    </button>
  );
}

export default function Player({
  playing,
  paused,
  loading,
  rate,
  currentIdx,
  totalParagraphs,
  viVoices,
  selectedVoiceName,
  onPlay,
  onPause,
  onResume,
  onStop,
  onSkipForward,
  onSkipBackward,
  onRateChange,
  onVoiceChange,
}: {
  playing: boolean;
  paused: boolean;
  loading: boolean;
  rate: number;
  currentIdx: number;
  totalParagraphs: number;
  viVoices: SpeechSynthesisVoice[];
  selectedVoiceName: string | null;
  onPlay: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onSkipForward: () => void;
  onSkipBackward: () => void;
  onRateChange: (rate: number) => void;
  onVoiceChange: (voiceName: string) => void;
}) {
  const [showSettings, setShowSettings] = useState(false);
  const {
    settings,
    setThemeId,
    setFontId,
    setFontSizeId,
    setTextColorId,
  } = useReaderSettingsContext();

  const progress =
    currentIdx >= 0 ? Math.round((currentIdx / totalParagraphs) * 100) : 0;

  const noVoice = viVoices.length === 0;

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-[var(--color-surface)] border-t border-[var(--color-border)] z-50">
      {playing && (
        <div className="w-full h-1 bg-[var(--color-border)]">
          <div
            className="h-full bg-[var(--color-accent)] transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      {showSettings && (
        <div className="px-4 py-3 border-t border-[var(--color-border)] max-h-[min(55vh,420px)] overflow-y-auto space-y-4">
          <div>
            <label className="text-xs text-[var(--color-text-muted)] block mb-2 font-medium">
              Bộ màu (tối)
            </label>
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
              {READER_THEMES.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setThemeId(t.id)}
                  className={`flex flex-col items-center gap-1.5 p-2 rounded-lg transition-all ring-2 ${
                    settings.themeId === t.id
                      ? "ring-[var(--color-accent)]"
                      : "ring-transparent hover:ring-[var(--color-border)]"
                  }`}
                  aria-label={t.name}
                  aria-pressed={settings.themeId === t.id}
                >
                  <span
                    className="w-full h-8 rounded-md border border-black/10 shadow-inner"
                    style={{
                      background: `linear-gradient(135deg, ${t.bg} 50%, ${t.surface} 50%)`,
                    }}
                  />
                  <span className="text-[10px] text-[var(--color-text-muted)]">
                    {t.name}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs text-[var(--color-text-muted)] block mb-2 font-medium">
              Màu chữ (Dịu mắt)
            </label>
            <div className="flex flex-wrap gap-1.5">
              {READER_TEXT_COLORS.map((c) => (
                <Chip
                  key={c.id}
                  active={(settings.textColorId || "default") === c.id}
                  onClick={() => setTextColorId(c.id)}
                >
                  <span style={{ color: (settings.textColorId || "default") === c.id ? "black" : (c.value || "inherit") }}>
                    {c.name}
                  </span>
                </Chip>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs text-[var(--color-text-muted)] block mb-2 font-medium">
              Font chữ
            </label>
            <div className="flex flex-wrap gap-1.5">
              {READER_FONTS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setFontId(f.id)}
                  style={{ fontFamily: f.family }}
                  className={`px-3 py-2 text-sm rounded-lg transition-colors ${
                    settings.fontId === f.id
                      ? "bg-[var(--color-accent)] text-black font-semibold"
                      : "bg-[var(--color-surface)] text-[var(--color-text)] ring-1 ring-[var(--color-border)] hover:opacity-90"
                  }`}
                >
                  {f.name}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs text-[var(--color-text-muted)] block mb-2 font-medium">
              Cỡ chữ
            </label>
            <div className="flex flex-wrap gap-1">
              {READER_FONT_SIZES.map((s) => (
                <Chip
                  key={s.id}
                  active={settings.fontSizeId === s.id}
                  onClick={() => setFontSizeId(s.id)}
                >
                  {s.name}
                </Chip>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs text-[var(--color-text-muted)] block mb-1">
              Giọng đọc
            </label>
            {noVoice ? (
              <div className="text-xs text-red-400 space-y-1">
                <p>Browser không có giọng tiếng Việt.</p>
                <p>Dùng Chrome hoặc Edge để có giọng đọc tốt nhất.</p>
              </div>
            ) : (
              <div className="flex flex-wrap gap-1">
                {viVoices.map((v) => (
                  <Chip
                    key={v.name}
                    active={selectedVoiceName === v.name}
                    onClick={() => onVoiceChange(v.name)}
                  >
                    {v.name.includes("Google")
                      ? "Google"
                      : v.name.includes("Microsoft")
                        ? "Microsoft"
                        : v.name}
                  </Chip>
                ))}
              </div>
            )}
          </div>

          <div>
            <label className="text-xs text-[var(--color-text-muted)] block mb-1">
              Tốc độ
            </label>
            <div className="flex flex-wrap gap-1">
              {RATES.map((r) => (
                <Chip
                  key={r}
                  active={rate === r}
                  onClick={() => onRateChange(r)}
                >
                  {r}x
                </Chip>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between max-w-3xl mx-auto px-4 py-3">
        <div className="flex items-center gap-2">
          {playing && (
            <button
              type="button"
              onClick={onSkipBackward}
              className="w-9 h-9 rounded-full bg-[var(--color-bg)] ring-1 ring-[var(--color-border)] flex items-center justify-center text-sm hover:opacity-80"
              aria-label="Quay lại đoạn trước"
            >
              {"⏮"}
            </button>
          )}

          <button
            type="button"
            onClick={
              playing && !paused
                ? onPause
                : playing && paused
                  ? onResume
                  : onPlay
            }
            disabled={loading || noVoice}
            className="w-12 h-12 rounded-full bg-[var(--color-accent)] text-black flex items-center justify-center text-xl font-bold disabled:opacity-50"
            aria-label={playing && !paused ? "Tạm dừng" : "Phát"}
          >
            {loading ? (
              <span className="animate-spin text-base">{"⏳"}</span>
            ) : playing && !paused ? (
              "⏸"
            ) : (
              "▶"
            )}
          </button>

          {playing && (
            <button
              type="button"
              onClick={onSkipForward}
              className="w-9 h-9 rounded-full bg-[var(--color-bg)] ring-1 ring-[var(--color-border)] flex items-center justify-center text-sm hover:opacity-80"
              aria-label="Chuyển đoạn tiếp"
            >
              {"⏭"}
            </button>
          )}

          {playing && (
            <button
              type="button"
              onClick={onStop}
              className="w-9 h-9 rounded-full bg-[var(--color-bg)] ring-1 ring-[var(--color-border)] flex items-center justify-center text-sm hover:opacity-80"
              aria-label="Dừng"
            >
              {"⏹"}
            </button>
          )}
        </div>

        <div className="text-sm text-[var(--color-text-muted)]">
          {noVoice
            ? "Không có giọng VN"
            : loading
              ? "Đang tải..."
              : currentIdx >= 0
                ? `${currentIdx + 1} / ${totalParagraphs}`
                : "Sẵn sàng"}
        </div>

        <button
          type="button"
          onClick={() => setShowSettings(!showSettings)}
          className={`px-3 py-2 text-sm rounded-lg transition-colors ${
            showSettings
              ? "bg-[var(--color-accent)] text-black font-semibold"
              : "bg-[var(--color-bg)] text-[var(--color-text-muted)] ring-1 ring-[var(--color-border)]"
          }`}
          aria-label="Cài đặt"
          aria-expanded={showSettings}
        >
          {"⚙"}
        </button>
      </div>
    </div>
  );
}
