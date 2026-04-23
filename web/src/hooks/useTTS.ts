"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { buildTTSChunks, type TTSChunk } from "@/lib/tts-chunks";

const PREFETCH_AHEAD = 5;

interface PreloadedAudio {
  audio: HTMLAudioElement;
  objectUrl: string;
}

async function fetchChunkAudio(
  text: string,
  rate: number,
  signal?: AbortSignal,
): Promise<Blob> {
  const res = await fetch("/api/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, rate }),
    signal,
  });
  if (!res.ok) throw new Error("TTS API error");
  return res.blob();
}

function isAbortError(error: unknown) {
  return error instanceof Error && error.name === "AbortError";
}

export function useTTS() {
  const [playing, setPlaying] = useState(false);
  const [paused, setPaused] = useState(false);
  const [currentIdx, setCurrentIdx] = useState(-1);
  const [rate, setRateState] = useState(1);
  const [loading, setLoading] = useState(false);
  const [activeRange, setActiveRange] = useState<{
    start: number;
    end: number;
  } | null>(null);
  const [totalChunks, setTotalChunks] = useState(0);

  const rateRef = useRef(1);
  const stoppedRef = useRef(false);
  const playIdRef = useRef(0);
  const onCompleteRef = useRef<(() => void) | null>(null);
  const chunksRef = useRef<TTSChunk[]>([]);
  const currentChunkIdxRef = useRef(-1);
  const sessionAbortRef = useRef<AbortController | null>(null);
  const preloadedRef = useRef<Map<number, PreloadedAudio>>(new Map());
  const preloadingRef = useRef<Map<number, Promise<PreloadedAudio | null>>>(
    new Map(),
  );
  const playChunkAtRef = useRef<
    (idx: number, playId: number) => Promise<void>
  >(async () => {});

  // --- Helpers ---

  const abortSession = useCallback(() => {
    sessionAbortRef.current?.abort();
    sessionAbortRef.current = null;
  }, []);

  const cleanupAllAudio = useCallback(() => {
    for (const [, entry] of preloadedRef.current) {
      entry.audio.pause();
      entry.audio.onended = null;
      entry.audio.onerror = null;
      entry.audio.removeAttribute("src");
      entry.audio.load();
      URL.revokeObjectURL(entry.objectUrl);
    }
    preloadedRef.current.clear();
    preloadingRef.current.clear();
  }, []);

  const abortAndCleanup = useCallback(() => {
    stoppedRef.current = true;
    abortSession();
    cleanupAllAudio();
    chunksRef.current = [];
    currentChunkIdxRef.current = -1;
    setPlaying(false);
    setPaused(false);
    setLoading(false);
    setCurrentIdx(-1);
    setActiveRange(null);
    setTotalChunks(0);
  }, [abortSession, cleanupAllAudio]);

  // --- Pre-load Audio elements ---

  const preloadChunk = useCallback(
    async (idx: number): Promise<PreloadedAudio | null> => {
      // Already preloaded
      const existing = preloadedRef.current.get(idx);
      if (existing) return existing;

      // Already preloading
      const inFlight = preloadingRef.current.get(idx);
      if (inFlight) return inFlight;

      const chunk = chunksRef.current[idx];
      if (!chunk) return null;

      const signal = sessionAbortRef.current?.signal;

      const promise: Promise<PreloadedAudio | null> = (async () => {
        try {
          const blob = await fetchChunkAudio(
            chunk.text,
            rateRef.current,
            signal,
          );
          if (stoppedRef.current) return null;

          const objectUrl = URL.createObjectURL(blob);
          const audio = new Audio();
          audio.preload = "auto";
          audio.src = objectUrl;

          let loadOk = false;
          try {
            await new Promise<void>((resolve, reject) => {
              audio.oncanplay = () => resolve();
              audio.onerror = () => reject(new Error("Audio load failed"));
            });
            loadOk = true;
          } catch {
            URL.revokeObjectURL(objectUrl);
            audio.removeAttribute("src");
          }

          if (stoppedRef.current || !loadOk) {
            if (loadOk) URL.revokeObjectURL(objectUrl);
            return null;
          }

          const entry: PreloadedAudio = { audio, objectUrl };
          preloadedRef.current.set(idx, entry);
          return entry;
        } catch (err) {
          if (isAbortError(err)) return null;
          throw err;
        } finally {
          preloadingRef.current.delete(idx);
        }
      })();

      preloadingRef.current.set(idx, promise);
      return promise;
    },
    [],
  );

  const prefetchAhead = useCallback(
    (fromIdx: number) => {
      const end = Math.min(fromIdx + PREFETCH_AHEAD, chunksRef.current.length);
      for (let i = fromIdx; i < end; i++) {
        if (
          !preloadedRef.current.has(i) &&
          !preloadingRef.current.has(i)
        ) {
          preloadChunk(i).catch(() => {});
        }
      }
      // Evict old entries
      for (const key of preloadedRef.current.keys()) {
        if (key < fromIdx - 1) {
          const entry = preloadedRef.current.get(key)!;
          entry.audio.pause();
          URL.revokeObjectURL(entry.objectUrl);
          preloadedRef.current.delete(key);
        }
      }
    },
    [preloadChunk],
  );

  // --- Core Playback ---

  const stopCurrentAudio = useCallback(() => {
    const entry = preloadedRef.current.get(currentChunkIdxRef.current);
    if (entry) {
      entry.audio.onended = null;
      entry.audio.onerror = null;
      entry.audio.pause();
      entry.audio.currentTime = 0;
    }
  }, []);

  const playChunkAt = useCallback(
    async (idx: number, playId: number) => {
      if (playIdRef.current !== playId) return;
      if (stoppedRef.current) return;

      // All chunks done
      if (idx >= chunksRef.current.length) {
        stopCurrentAudio();
        setPlaying(false);
        setPaused(false);
        setLoading(false);
        setCurrentIdx(-1);
        setActiveRange(null);
        currentChunkIdxRef.current = -1;
        const cb = onCompleteRef.current;
        onCompleteRef.current = null;
        if (cb) cb();
        return;
      }

      currentChunkIdxRef.current = idx;
      const chunk = chunksRef.current[idx];

      setCurrentIdx(chunk.startParagraphIdx);
      setActiveRange({
        start: chunk.startParagraphIdx,
        end: chunk.endParagraphIdx,
      });

      prefetchAhead(idx + 1);

      const preloaded = await preloadChunk(idx);
      if (playIdRef.current !== playId || stoppedRef.current) return;

      // Failed to preload — skip
      if (!preloaded) {
        playChunkAtRef.current(idx + 1, playId);
        return;
      }

      // Stop other playing audio, reset this one to start
      stopCurrentAudio();
      preloaded.audio.currentTime = 0;

      preloaded.audio.onended = () => {
        if (playIdRef.current !== playId) return;
        if (stoppedRef.current) return;
        playChunkAtRef.current(idx + 1, playId);
      };

      preloaded.audio.onerror = () => {
        if (playIdRef.current !== playId) return;
        if (!stoppedRef.current) playChunkAtRef.current(idx + 1, playId);
      };

      try {
        await preloaded.audio.play();
        setLoading(false);
      } catch {
        if (!stoppedRef.current) abortAndCleanup();
      }
    },
    [stopCurrentAudio, abortAndCleanup, prefetchAhead, preloadChunk],
  );

  useEffect(() => {
    playChunkAtRef.current = playChunkAt;
  }, [playChunkAt]);

  // --- Public API ---

  const prepare = useCallback((_key: string, paragraphs: string[]) => {
    if (!paragraphs.length) return;
    chunksRef.current = buildTTSChunks(paragraphs);
  }, []);

  const play = useCallback(
    (_key: string, paragraphs: string[]) => {
      if (!paragraphs.length) return;

      stoppedRef.current = false;
      const newPlayId = ++playIdRef.current;
      stopCurrentAudio();
      abortSession();
      cleanupAllAudio();

      sessionAbortRef.current = new AbortController();
      chunksRef.current = buildTTSChunks(paragraphs);
      currentChunkIdxRef.current = -1;

      setPlaying(true);
      setPaused(false);
      setLoading(true);
      setTotalChunks(chunksRef.current.length);

      playChunkAt(0, newPlayId);
    },
    [stopCurrentAudio, abortSession, cleanupAllAudio, playChunkAt],
  );

  const pause = useCallback(() => {
    const entry = preloadedRef.current.get(currentChunkIdxRef.current);
    if (entry) entry.audio.pause();
    setPaused(true);
  }, []);

  const resume = useCallback(async () => {
    const entry = preloadedRef.current.get(currentChunkIdxRef.current);
    if (entry) await entry.audio.play();
    setPaused(false);
  }, []);

  const stop = useCallback(() => {
    abortAndCleanup();
  }, [abortAndCleanup]);

  const skipForward = useCallback(() => {
    if (currentChunkIdxRef.current < 0) return;
    const newPlayId = ++playIdRef.current;
    const nextIdx = currentChunkIdxRef.current + 1;
    if (nextIdx >= chunksRef.current.length) return;
    playChunkAt(nextIdx, newPlayId);
  }, [playChunkAt]);

  const skipBackward = useCallback(() => {
    if (currentChunkIdxRef.current < 0) return;
    const newPlayId = ++playIdRef.current;
    const entry = preloadedRef.current.get(currentChunkIdxRef.current);
    const elapsed = entry ? entry.audio.currentTime : 0;
    const targetIdx =
      elapsed > 3
        ? currentChunkIdxRef.current
        : Math.max(0, currentChunkIdxRef.current - 1);
    playChunkAt(targetIdx, newPlayId);
  }, [playChunkAt]);

  const setRate = useCallback(
    (newRate: number) => {
      if (rateRef.current === newRate) return;
      rateRef.current = newRate;
      abortAndCleanup();
      stoppedRef.current = false;
      setRateState(newRate);
    },
    [abortAndCleanup],
  );

  const setOnChapterComplete = useCallback((cb: () => void) => {
    onCompleteRef.current = cb;
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stoppedRef.current = true;
      abortSession();
      cleanupAllAudio();
    };
  }, [abortSession, cleanupAllAudio]);

  return {
    playing,
    paused,
    loading,
    currentIdx,
    activeRange,
    rate,
    totalChunks,
    currentChunkIdx: currentChunkIdxRef.current,
    play,
    prepare,
    pause,
    resume,
    stop,
    skipForward,
    skipBackward,
    setRate,
    setOnChapterComplete,
  };
}
