"use client";

import { useState } from "react";

const RATES = [0.75, 1, 1.25, 1.5, 2];

export default function Player({
  playing,
  paused,
  loading,
  rate,
  currentIdx,
  totalParagraphs,
  onPlay,
  onPause,
  onResume,
  onStop,
  onSkipForward,
  onSkipBackward,
  onRateChange,
}: {
  playing: boolean;
  paused: boolean;
  loading: boolean;
  rate: number;
  currentIdx: number;
  totalParagraphs: number;
  onPlay: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onSkipForward: () => void;
  onSkipBackward: () => void;
  onRateChange: (rate: number) => void;
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

          <p className="text-xs text-[var(--color-text-muted)]">
            Edge TTS - vi-VN-HoaiMyNeural
          </p>
        </div>
      )}

      {/* Main controls */}
      <div className="flex items-center justify-between max-w-3xl mx-auto px-4 py-3">
        <div className="flex items-center gap-2">
          {/* Skip backward */}
          {playing && (
            <button
              onClick={onSkipBackward}
              className="w-9 h-9 rounded-full bg-gray-700 flex items-center justify-center text-sm hover:bg-gray-600"
              aria-label="Quay lại đoạn trước"
            >
              {"⏮"}
            </button>
          )}

          {/* Play / Pause */}
          <button
            onClick={
              playing && !paused
                ? onPause
                : playing && paused
                  ? onResume
                  : onPlay
            }
            disabled={loading}
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

          {/* Skip forward */}
          {playing && (
            <button
              onClick={onSkipForward}
              className="w-9 h-9 rounded-full bg-gray-700 flex items-center justify-center text-sm hover:bg-gray-600"
              aria-label="Chuyển đoạn tiếp"
            >
              {"⏭"}
            </button>
          )}

          {/* Stop */}
          {playing && (
            <button
              onClick={onStop}
              className="w-9 h-9 rounded-full bg-gray-700 flex items-center justify-center text-sm hover:bg-gray-600"
              aria-label="Dừng"
            >
              {"⏹"}
            </button>
          )}
        </div>

        <div className="text-sm text-[var(--color-text-muted)]">
          {loading
            ? "Đang tải..."
            : currentIdx >= 0
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
          {"⚙"}
        </button>
      </div>
    </div>
  );
}
