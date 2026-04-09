"use client";

const RATES = [0.75, 1, 1.25, 1.5, 2];

export default function Player({
  playing,
  paused,
  rate,
  currentIdx,
  totalParagraphs,
  onPlay,
  onPause,
  onResume,
  onStop,
  onRateChange,
}: {
  playing: boolean;
  paused: boolean;
  rate: number;
  currentIdx: number;
  totalParagraphs: number;
  onPlay: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onRateChange: (rate: number) => void;
}) {
  const progress =
    currentIdx >= 0 ? Math.round((currentIdx / totalParagraphs) * 100) : 0;

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-[var(--color-surface)] border-t border-gray-800 px-4 py-3 z-50">
      {playing && (
        <div className="w-full h-1 bg-gray-800 rounded-full mb-2">
          <div
            className="h-full bg-[var(--color-accent)] rounded-full transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      <div className="flex items-center justify-between max-w-2xl mx-auto">
        <div className="flex items-center gap-3">
          <button
            onClick={playing && !paused ? onPause : playing && paused ? onResume : onPlay}
            className="w-12 h-12 rounded-full bg-[var(--color-accent)] text-black flex items-center justify-center text-xl font-bold"
            aria-label={playing && !paused ? "T\u1EA1m d\u1EEBng" : "Ph\u00E1t"}
          >
            {playing && !paused ? "\u23F8" : "\u25B6"}
          </button>

          {playing && (
            <button
              onClick={onStop}
              className="w-10 h-10 rounded-full bg-gray-700 flex items-center justify-center text-lg"
              aria-label="D\u1EEBng"
            >
              {"\u23F9"}
            </button>
          )}
        </div>

        <div className="text-sm text-[var(--color-text-muted)]">
          {currentIdx >= 0
            ? `${currentIdx + 1} / ${totalParagraphs}`
            : "S\u1EB5n s\u00E0ng"}
        </div>

        <div className="flex gap-1">
          {RATES.map((r) => (
            <button
              key={r}
              onClick={() => onRateChange(r)}
              className={`px-2 py-1 text-xs rounded ${
                rate === r
                  ? "bg-[var(--color-accent)] text-black font-bold"
                  : "bg-gray-700 text-[var(--color-text-muted)]"
              }`}
            >
              {r}x
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
