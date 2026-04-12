"use client";

import { useState, useCallback, useRef, useEffect } from "react";

async function fetchAudioBlob(
  paragraphs: string[],
  rate: number,
  signal?: AbortSignal,
): Promise<Blob> {
  const res = await fetch("/api/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paragraphs, rate }),
    signal,
  });

  if (!res.ok) {
    throw new Error("TTS API error");
  }

  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("audio/")) {
    throw new Error(`Unexpected TTS content type: ${contentType}`);
  }

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
  const [activeRange, setActiveRange] = useState<{ start: number; end: number } | null>(null);

  const paragraphsRef = useRef<string[]>([]);
  const rateRef = useRef(1);
  const stoppedRef = useRef(false);
  const onCompleteRef = useRef<(() => void) | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const pendingFetchRef = useRef<AbortController | null>(null);
  const cacheRef = useRef<Map<string, Promise<Blob | null>>>(new Map());

  const clearCache = useCallback(() => {
    pendingFetchRef.current?.abort();
    pendingFetchRef.current = null;
    cacheRef.current.clear();
  }, []);

  const revokeCurrentUrl = useCallback(() => {
    if (!objectUrlRef.current) return;
    URL.revokeObjectURL(objectUrlRef.current);
    objectUrlRef.current = null;
  }, []);

  const resetAudioElement = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.onended = null;
      audio.onerror = null;
      audio.ontimeupdate = null;
      audio.removeAttribute("src");
      audio.load();
      audioRef.current = null;
    }

    revokeCurrentUrl();
  }, [revokeCurrentUrl]);

  const resetState = useCallback(() => {
    resetAudioElement();
    setCurrentIdx(-1);
    setActiveRange(null);
    setLoading(false);
  }, [resetAudioElement]);

  const cleanup = useCallback(() => {
    resetState();
    clearCache();
    paragraphsRef.current = [];
  }, [clearCache, resetState]);

  const prepare = useCallback(
    (contentKey: string, paragraphs: string[]) => {
      if (!paragraphs.length) return;

      const cacheKey = `${contentKey}:${rateRef.current}`;

      paragraphsRef.current = paragraphs;

      if (cacheRef.current.has(cacheKey)) {
        return;
      }

      const controller = new AbortController();
      pendingFetchRef.current = controller;

      const promise = fetchAudioBlob(paragraphs, rateRef.current, controller.signal)
        .catch((error) => {
          cacheRef.current.delete(cacheKey);
          if (isAbortError(error)) {
            return null;
          }
          throw error;
        })
        .finally(() => {
          if (pendingFetchRef.current === controller) {
            pendingFetchRef.current = null;
          }
        });

      cacheRef.current.set(cacheKey, promise);
    },
    [],
  );

  const play = useCallback(
    async (contentKey: string, paragraphs: string[]) => {
      if (!paragraphs.length) return;

      const cacheKey = `${contentKey}:${rateRef.current}`;
      stoppedRef.current = false;
      paragraphsRef.current = paragraphs;
      prepare(contentKey, paragraphs);

      setLoading(true);
      setPlaying(true);
      setPaused(false);

      try {
        const blob = await cacheRef.current.get(cacheKey);
        if (stoppedRef.current || !blob) return;

        resetAudioElement();
        const objectUrl = URL.createObjectURL(blob);
        objectUrlRef.current = objectUrl;
        const audio = new Audio(objectUrl);
        audio.preload = "auto";
        audioRef.current = audio;
        audio.currentTime = 0;
        audio.playbackRate = rateRef.current;

        audio.ontimeupdate = () => {
          if (!Number.isFinite(audio.duration) || audio.duration <= 0) {
            return;
          }

          const progress = Math.min(audio.currentTime / audio.duration, 0.999);
          const paragraphIdx = Math.min(
            paragraphsRef.current.length - 1,
            Math.floor(progress * paragraphsRef.current.length),
          );

          setCurrentIdx(paragraphIdx);
          setActiveRange({ start: paragraphIdx, end: paragraphIdx });
        };

        audio.onended = () => {
          if (stoppedRef.current) return;

          resetAudioElement();
          setPlaying(false);
          setPaused(false);
          setLoading(false);
          setCurrentIdx(-1);
          setActiveRange(null);

          const callback = onCompleteRef.current;
          onCompleteRef.current = null;
          if (callback) {
            callback();
          }
        };

        audio.onerror = () => {
          resetAudioElement();
          setPlaying(false);
          setPaused(false);
          setLoading(false);
        };

        setCurrentIdx(0);
        setActiveRange({ start: 0, end: 0 });
        await audio.play();
        setLoading(false);
      } catch {
        if (!stoppedRef.current) {
          resetAudioElement();
          setPlaying(false);
          setPaused(false);
          setLoading(false);
        }
      }
    },
    [prepare, resetAudioElement],
  );

  const pause = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;

    audio.pause();
    setPaused(true);
  }, []);

  const resume = useCallback(async () => {
    const audio = audioRef.current;
    if (!audio) return;

    await audio.play();
    setPaused(false);
  }, []);

  const stop = useCallback(() => {
    stoppedRef.current = true;
    resetAudioElement();
    setPlaying(false);
    setPaused(false);
    setLoading(false);
    setCurrentIdx(-1);
    setActiveRange(null);
  }, [resetAudioElement]);

  const setRate = useCallback(
    (newRate: number) => {
      if (rateRef.current === newRate) return;

      rateRef.current = newRate;
      if (audioRef.current) {
        audioRef.current.playbackRate = newRate;
      }
      clearCache();
      setRateState(newRate);
    },
    [clearCache],
  );

  const setOnChapterComplete = useCallback((cb: () => void) => {
    onCompleteRef.current = cb;
  }, []);

  useEffect(() => cleanup, [cleanup]);

  return {
    playing,
    paused,
    loading,
    currentIdx,
    activeRange,
    rate,
    play,
    prepare,
    pause,
    resume,
    stop,
    setRate,
    setOnChapterComplete,
  };
}
