"use client";

import { useState } from "react";

const RATES = [0.75, 1, 1.25, 1.5, 2];

export default function Player({
  playing,
  paused,
  rate,
  currentIdx,
  totalParagraphs,
  voices,
  selectedVoice,
  onPlay,
  onPause,
  onResume,
  onStop,
  onRateChange,
  onVoiceChange,
}: {
  playing: boolean;
  paused: boolean;
  rate: number;
  currentIdx: number;
  totalParagraphs: number;
  voices: SpeechSynthesisVoice[];
  selectedVoice: SpeechSynthesisVoice | null;
  onPlay: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onRateChange: (rate: number) => void;
  onVoiceChange: (voice: SpeechSynthesisVoice) => void;
}) {
  const [showSettings, setShowSettings] = useState(false);
  const progress =
    currentIdx >= 0 ? Math.round((currentIdx / totalParagraphs) * 100) : 0;

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-[var(--color-surface)] border-t border-gray-800 z-50">
      {playing && (
        <div className="w-full h-1 bg-gray-800 rounded-full">
          <div
            className="h-full bg-[var(--color-accent)] rounded-full transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      {/* Settings panel */}
      {showSettings && (
        <div className="px-4 py-3 border-t border-gray-800 space-y-3">
          {/* Voice selector */}
          {voices.length > 0 && (
            <div>
              <label className="text-xs text-[var(--color-text-muted)] block mb-1">
                Giọng đọc
              </label>
              <div className="flex flex-wrap gap-1">
                {voices.map((v, i) => (
                  <button
                    key={i}
                    onClick={() => onVoiceChange(v)}
                    className={`px-3 py-1.5 text-xs rounded-full ${
                      selectedVoice?.name === v.name
                        ? "bg-[var(--color-accent)] text-black font-bold"
                        : "bg-gray-700 text-[var(--color-text-muted)] hover:bg-gray-600"
                    }`}
                  >
                    {v.name.replace("Google ", "").replace("Microsoft ", "")}
                  </button>
                ))}
              </div>
            </div>
          )}

          {voices.length === 0 && (
            <p className="text-xs text-[var(--color-text-muted)]">
              Trình duyệt không có giọng tiếng Việt. Thử dùng Chrome.
            </p>
          )}

          {/* Speed control */}
          <div>
            <label className="text-xs text-[var(--color-text-muted)] block mb-1">
              Tốc độ
            </label>
            <div className="flex gap-1">
              {RATES.map((r) => (
                <button
                  key={r}
                  onClick={() => onRateChange(r)}
                  className={`px-3 py-1.5 text-xs rounded-full ${
                    rate === r
                      ? "bg-[var(--color-accent)] text-black font-bold"
                      : "bg-gray-700 text-[var(--color-text-muted)] hover:bg-gray-600"
                  }`}
                >
                  {r}x
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Main controls */}
      <div className="flex items-center justify-between max-w-3xl mx-auto px-4 py-3">
        <div className="flex items-center gap-3">
          <button
            onClick={
              playing && !paused
                ? onPause
                : playing && paused
                  ? onResume
                  : onPlay
            }
            className="w-12 h-12 rounded-full bg-[var(--color-accent)] text-black flex items-center justify-center text-xl font-bold"
            aria-label={playing && !paused ? "Tạm dừng" : "Phát"}
          >
            {playing && !paused ? "\u23F8" : "\u25B6"}
          </button>

          {playing && (
            <button
              onClick={onStop}
              className="w-10 h-10 rounded-full bg-gray-700 flex items-center justify-center text-lg"
              aria-label="Dừng"
            >
              {"\u23F9"}
            </button>
          )}
        </div>

        <div className="text-sm text-[var(--color-text-muted)]">
          {currentIdx >= 0
            ? `${currentIdx + 1} / ${totalParagraphs}`
            : "Sẵn sàng"}
        </div>

        <button
          onClick={() => setShowSettings(!showSettings)}
          className={`px-3 py-2 text-sm rounded-lg ${
            showSettings
              ? "bg-[var(--color-accent)] text-black"
              : "bg-gray-700 text-[var(--color-text-muted)]"
          }`}
          aria-label="Cài đặt"
        >
          {"\u2699"}
        </button>
      </div>
    </div>
  );
}
