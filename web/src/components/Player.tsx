"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useReaderSettingsContext } from "@/context/ReaderSettingsContext";
import {
  READER_FONTS,
  READER_FONT_SIZES,
  READER_THEMES,
  READER_TEXT_COLORS,
} from "@/lib/reader-settings";
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  Stop,
  SlidersHorizontal,
  X,
  CircleNotch,
  PlayCircle,
} from "@/components/icons";
import type { TTSVoice } from "@/lib/tts-voices";

const MIN_RATE = 1;
const MAX_RATE = 6;
const RATE_STEP = 0.1;

function Chip({
  active,
  onClick,
  children,
  className = "",
  title,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={`px-4 py-1.5 min-h-[44px] inline-flex items-center justify-center text-xs rounded-full transition-all duration-200 active:scale-95 ${className} ${
        active
          ? "bg-[var(--color-accent)] text-black font-semibold"
          : "bg-[var(--color-surface-2)] text-[var(--color-text-muted)] border border-[var(--color-border)] hover:opacity-90"
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
  voices,
  selectedVoiceName,
  onPlay,
  onPlayFromHere,
  onPause,
  onResume,
  onStop,
  onSkipForward,
  onSkipBackward,
  onRateChange,
  onVoiceChange,
  hidden = false,
}: {
  playing: boolean;
  paused: boolean;
  loading: boolean;
  rate: number;
  currentIdx: number;
  totalParagraphs: number;
  voices: TTSVoice[];
  selectedVoiceName: string | null;
  onPlay: () => void;
  onPlayFromHere?: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onSkipForward: () => void;
  onSkipBackward: () => void;
  onRateChange: (rate: number) => void;
  onVoiceChange: (voiceName: string) => void;
  hidden?: boolean;
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
    totalParagraphs > 0 && currentIdx >= 0
      ? Math.round((currentIdx / totalParagraphs) * 100)
      : 0;

  // Bar must stay visible while TTS is active (playing/paused/loading) or the
  // settings sheet is open. Otherwise auto-follow scrolling during playback
  // sets `hidden` (scroll down) → the settings button slides away unreachable,
  // and the sheet can never be opened while TTS reads.
  const barHidden = hidden && !showSettings && !playing && !loading;

  useEffect(() => {
    if (!showSettings) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setShowSettings(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [showSettings]);

  return (
    <>
      {/* Floating player bar */}
      <div className={`fixed bottom-[calc(1.5rem+env(safe-area-inset-bottom))] left-1/2 -translate-x-1/2 w-[calc(100%-2rem)] max-w-2xl glass-panel rounded-2xl z-40 transition-all duration-500 ease-out ${barHidden ? "translate-y-32 opacity-0 md:translate-y-0 md:opacity-100" : "translate-y-0 opacity-100"}`}>
        {playing && (
          <div className="absolute top-0 left-0 right-0 h-1 bg-[var(--color-border)] rounded-t-2xl overflow-hidden">
            <div
              className="h-full bg-[var(--color-accent)] transition-[width] duration-700 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        )}

        <div className="flex items-center justify-between px-5 py-3">
          <div className="flex items-center gap-3">
            {!playing && onPlayFromHere && (
              <button
                type="button"
                onClick={onPlayFromHere}
                className="px-3 h-11 rounded-full bg-black/20 hover:bg-black/40 flex items-center gap-1.5 justify-center text-xs font-medium transition-all duration-200 active:scale-90 border border-white/5 whitespace-nowrap"
                aria-label="Đọc từ đoạn đang xem"
                title="Đọc từ đoạn đang xem"
              >
                <PlayCircle size={18} />
                Từ đây
              </button>
            )}
            {playing && (
              <button
                type="button"
                onClick={onSkipBackward}
                className="w-11 h-11 rounded-full bg-black/20 hover:bg-black/40 flex items-center justify-center transition-all duration-200 active:scale-90 border border-white/5"
                aria-label="Quay lại đoạn trước"
              >
                <SkipBack size={20} />
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
              disabled={loading}
              className="w-14 h-14 rounded-full bg-[var(--color-accent)] text-black flex items-center justify-center disabled:opacity-50 active:scale-95 transition-transform duration-200"
              aria-label={playing && !paused ? "Tạm dừng" : "Phát"}
            >
              {loading ? (
                <CircleNotch size={24} weight="bold" className="animate-spin" />
              ) : playing && !paused ? (
                <Pause size={24} weight="fill" />
              ) : (
                <Play size={24} weight="fill" />
              )}
            </button>

            {playing && (
              <button
                type="button"
                onClick={onSkipForward}
                className="w-11 h-11 rounded-full bg-black/20 hover:bg-black/40 flex items-center justify-center transition-all duration-200 active:scale-90 border border-white/5"
                aria-label="Chuyển đoạn tiếp"
              >
                <SkipForward size={20} />
              </button>
            )}

            {playing && (
              <button
                type="button"
                onClick={onStop}
                className="w-11 h-11 rounded-full bg-black/20 hover:bg-black/40 flex items-center justify-center transition-all duration-200 active:scale-90 border border-white/5"
                aria-label="Dừng"
              >
                <Stop size={20} />
              </button>
            )}
          </div>

          <div className="text-sm font-medium tracking-wide text-[var(--color-text-muted)] bg-black/20 px-3 py-1.5 rounded-full border border-white/5">
            {loading
              ? "Đang tải..."
              : currentIdx >= 0
                ? `${currentIdx + 1} / ${totalParagraphs}`
                : "Sẵn sàng"}
          </div>

          <button
            type="button"
            onClick={() => setShowSettings(true)}
            className="w-11 h-11 rounded-full flex items-center justify-center transition-all duration-200 active:scale-90 bg-black/20 text-[var(--color-text-muted)] border border-white/5 hover:bg-white/10 hover:text-white"
            aria-label="Cài đặt"
            aria-expanded={showSettings}
          >
            <SlidersHorizontal size={20} />
          </button>
        </div>
      </div>

      {/* Settings bottom sheet */}
      {showSettings && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-fade-in"
            onClick={() => setShowSettings(false)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Tùy chỉnh đọc"
            className="relative w-full sm:max-w-2xl bg-[var(--color-surface)] sm:rounded-2xl rounded-t-2xl border border-[var(--color-border)] shadow-2xl overflow-hidden animate-slide-up flex flex-col max-h-[85vh]"
          >
            <div className="flex justify-between items-center p-5 border-b border-[var(--color-border)]">
              <h3 className="text-lg font-bold">Tùy chỉnh</h3>
              <button
                onClick={() => setShowSettings(false)}
                className="w-11 h-11 rounded-full bg-black/20 hover:bg-black/40 flex items-center justify-center transition-all duration-200 active:scale-90 border border-white/5"
                aria-label="Đóng"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-5 overflow-y-auto space-y-8 custom-scrollbar">
              <div>
                <label className="text-xs text-[var(--color-text-muted)] block mb-3 font-semibold uppercase tracking-wider">
                  Bộ màu (tối)
                </label>
                <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
                  {READER_THEMES.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => setThemeId(t.id)}
                      className={`flex flex-col items-center gap-2 p-2 rounded-xl transition-all duration-200 active:scale-95 border ${
                        settings.themeId === t.id
                          ? "border-[var(--color-accent)] bg-[var(--color-accent)]/10"
                          : "border-transparent hover:bg-white/5"
                      }`}
                      aria-label={t.name}
                      aria-pressed={settings.themeId === t.id}
                    >
                      <span
                        className="w-full h-10 rounded-lg border border-black/20 shadow-inner"
                        style={{
                          background: `linear-gradient(135deg, ${t.bg} 50%, ${t.surface} 50%)`,
                        }}
                      />
                      <span className="text-[10px] text-[var(--color-text-muted)] font-medium">
                        {t.name}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-xs text-[var(--color-text-muted)] block mb-3 font-semibold uppercase tracking-wider">
                  Màu chữ (Dịu mắt)
                </label>
                <div className="flex flex-wrap gap-2">
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
                <label className="text-xs text-[var(--color-text-muted)] block mb-3 font-semibold uppercase tracking-wider">
                  Font chữ
                </label>
                <div className="flex flex-wrap gap-2">
                  {READER_FONTS.map((f) => (
                    <button
                      key={f.id}
                      type="button"
                      onClick={() => setFontId(f.id)}
                      style={{ fontFamily: f.family }}
                      className={`px-4 py-2.5 min-h-[44px] inline-flex items-center justify-center text-sm rounded-full transition-all duration-200 active:scale-95 ${
                        settings.fontId === f.id
                          ? "bg-[var(--color-accent)] text-black font-semibold"
                          : "bg-[var(--color-surface-2)] text-[var(--color-text)] border border-[var(--color-border)] hover:opacity-90"
                      }`}
                    >
                      {f.name}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-xs text-[var(--color-text-muted)] block mb-3 font-semibold uppercase tracking-wider">
                  Cỡ chữ
                </label>
                <div className="flex flex-wrap gap-2">
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
                <label className="text-xs text-[var(--color-text-muted)] block mb-3 font-semibold uppercase tracking-wider">
                  Giọng đọc & Tốc độ
                </label>
                <div className="space-y-4">
                  <div className="flex flex-wrap gap-2">
                    {voices.map((v) => (
                      <Chip
                        key={v.name}
                        active={selectedVoiceName === v.name}
                        onClick={() => onVoiceChange(v.name)}
                        title={
                          v.engine === "google"
                            ? "Giọng Google Translate (miễn phí) — giống engine Google Translate của Read Aloud"
                            : "Microsoft Edge Neural (chất lượng cao)"
                        }
                      >
                        {v.label}
                      </Chip>
                    ))}
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium">
                        Tốc độ
                      </span>
                      <span
                        className="text-sm font-semibold text-[var(--color-accent)] tabular-nums"
                        aria-live="polite"
                      >
                        {rate.toFixed(1)}x
                      </span>
                    </div>
                    <input
                      type="range"
                      min={MIN_RATE}
                      max={MAX_RATE}
                      step={RATE_STEP}
                      value={rate}
                      onChange={(e) =>
                        onRateChange(parseFloat(e.target.value))
                      }
                      aria-label="Tốc độ đọc"
                      className="w-full min-h-[44px] accent-[var(--color-accent)] cursor-pointer"
                    />
                    <div className="flex justify-between text-[10px] text-[var(--color-text-muted)] font-medium">
                      <span>{MIN_RATE.toFixed(1)}x</span>
                      <span>{MAX_RATE.toFixed(1)}x</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
