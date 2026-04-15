"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { buildTTSChunks, type TTSChunk } from "@/lib/tts-chunks";

const PREFETCH_AHEAD = 2;

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

  const rateRef = useRef(1);
  const stoppedRef = useRef(false);
  const onCompleteRef = useRef<(() => void) | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const chunksRef = useRef<TTSChunk[]>([]);
  const currentChunkIdxRef = useRef(-1);
  const sessionAbortRef = useRef<AbortController | null>(null);
  const blobCacheRef = useRef<Map<string, Promise<Blob | null>>>(new Map());
  const playChunkAtRef = useRef<(idx: number) => Promise<void>>(async () => {});

  function blobCacheKey(text: string, r: number) {
    return `${r}:${text}`;
  }

  const revokeUrl = useCallback(() => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
  }, []);

  const cleanupAudio = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.onended = null;
      audio.onerror = null;
      audio.removeAttribute("src");
      audio.load();
      audioRef.current = null;
    }
    revokeUrl();
  }, [revokeUrl]);

  const abortSession = useCallback(() => {
    sessionAbortRef.current?.abort();
    sessionAbortRef.current = null;
  }, []);

  const fullReset = useCallback(() => {
    stoppedRef.current = true;
    abortSession();
    cleanupAudio();
    blobCacheRef.current.clear();
    chunksRef.current = [];
    currentChunkIdxRef.current = -1;
    setPlaying(false);
    setPaused(false);
    setLoading(false);
    setCurrentIdx(-1);
    setActiveRange(null);
  }, [abortSession, cleanupAudio]);

  const getOrFetchChunk = useCallback(
    (chunkIdx: number): Promise<Blob | null> | null => {
      const chunk = chunksRef.current[chunkIdx];
      if (!chunk) return null;

      const key = blobCacheKey(chunk.text, rateRef.current);
      const existing = blobCacheRef.current.get(key);
      if (existing) return existing;

      const signal = sessionAbortRef.current?.signal;
      const promise: Promise<Blob | null> = fetchChunkAudio(
        chunk.text,
        rateRef.current,
        signal,
      ).catch((err) => {
        blobCacheRef.current.delete(key);
        if (isAbortError(err)) return null;
        throw err;
      });

      blobCacheRef.current.set(key, promise);
      return promise;
    },
    [],
  );

  const prefetchAhead = useCallback(
    (fromIdx: number) => {
      const end = Math.min(fromIdx + PREFETCH_AHEAD, chunksRef.current.length);
      for (let i = fromIdx; i < end; i++) {
        getOrFetchChunk(i);
      }
    },
    [getOrFetchChunk],
  );

  const playChunkAt = useCallback(
    async (idx: number) => {
      if (stoppedRef.current) return;

      if (idx >= chunksRef.current.length) {
        cleanupAudio();
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

      const blobPromise = getOrFetchChunk(idx);
      if (!blobPromise) return;

      try {
        const blob = await blobPromise;
        if (stoppedRef.current || !blob) return;

        cleanupAudio();
        const url = URL.createObjectURL(blob);
        objectUrlRef.current = url;

        const audio = new Audio(url);
        audio.preload = "auto";
        audioRef.current = audio;

        audio.onended = () => {
          if (stoppedRef.current) return;
          playChunkAtRef.current(idx + 1);
        };

        audio.onerror = () => {
          if (!stoppedRef.current) fullReset();
        };

        await audio.play();
        setLoading(false);
      } catch {
        if (!stoppedRef.current) fullReset();
      }
    },
    [cleanupAudio, fullReset, getOrFetchChunk, prefetchAhead],
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
      abortSession();
      cleanupAudio();
      blobCacheRef.current.clear();

      sessionAbortRef.current = new AbortController();
      chunksRef.current = buildTTSChunks(paragraphs);

      setPlaying(true);
      setPaused(false);
      setLoading(true);

      playChunkAt(0);
    },
    [abortSession, cleanupAudio, playChunkAt],
  );

  const pause = useCallback(() => {
    audioRef.current?.pause();
    setPaused(true);
  }, []);

  const resume = useCallback(async () => {
    await audioRef.current?.play();
    setPaused(false);
  }, []);

  const stop = useCallback(() => {
    fullReset();
  }, [fullReset]);

  const setRate = useCallback(
    (newRate: number) => {
      if (rateRef.current === newRate) return;
      rateRef.current = newRate;
      fullReset();
      stoppedRef.current = false;
      setRateState(newRate);
    },
    [fullReset],
  );

  const setOnChapterComplete = useCallback((cb: () => void) => {
    onCompleteRef.current = cb;
  }, []);

  useEffect(() => {
    const cache = blobCacheRef.current;
    return () => {
      stoppedRef.current = true;
      abortSession();
      cleanupAudio();
      cache.clear();
    };
  }, [abortSession, cleanupAudio]);

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
