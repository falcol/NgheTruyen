"use client";

import { useState, useCallback, useRef, useEffect } from "react";

const PREFETCH_AHEAD = 2;

async function fetchAudioBuffer(
  ctx: AudioContext,
  text: string,
  rate: number
): Promise<AudioBuffer> {
  const res = await fetch("/api/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, rate }),
  });
  if (!res.ok) throw new Error("TTS API error");
  const arrayBuffer = await res.arrayBuffer();
  return ctx.decodeAudioData(arrayBuffer);
}

export function useTTS() {
  const [playing, setPlaying] = useState(false);
  const [paused, setPaused] = useState(false);
  const [currentIdx, setCurrentIdx] = useState(-1);
  const [rate, setRateState] = useState(1);
  const [loading, setLoading] = useState(false);

  const paragraphsRef = useRef<string[]>([]);
  const rateRef = useRef(1);
  const stoppedRef = useRef(false);
  const onCompleteRef = useRef<(() => void) | null>(null);

  // Web Audio API refs
  const ctxRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<AudioBufferSourceNode | null>(null);
  const pausedAtRef = useRef(0);
  const startedAtRef = useRef(0);
  const currentBufferRef = useRef<AudioBuffer | null>(null);

  // Prefetch cache: idx -> Promise<AudioBuffer>
  const cacheRef = useRef<Map<number, Promise<AudioBuffer>>>(new Map());

  const speakNextRef = useRef<(idx: number) => Promise<void>>(undefined);

  const getCtx = useCallback(() => {
    if (!ctxRef.current) {
      ctxRef.current = new AudioContext();
    }
    return ctxRef.current;
  }, []);

  const stopSource = useCallback(() => {
    if (sourceRef.current) {
      try { sourceRef.current.stop(); } catch {}
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
  }, []);

  const clearCache = useCallback(() => {
    cacheRef.current.clear();
  }, []);

  const cleanup = useCallback(() => {
    stopSource();
    clearCache();
    currentBufferRef.current = null;
    pausedAtRef.current = 0;
    startedAtRef.current = 0;
  }, [stopSource, clearCache]);

  const prefetch = useCallback((idx: number) => {
    const cache = cacheRef.current;
    if (cache.has(idx) || idx >= paragraphsRef.current.length) return;
    const ctx = getCtx();
    cache.set(idx, fetchAudioBuffer(ctx, paragraphsRef.current[idx], rateRef.current));
  }, [getCtx]);

  const playBuffer = useCallback((buffer: AudioBuffer, offset = 0) => {
    const ctx = getCtx();
    if (ctx.state === "suspended") ctx.resume();

    stopSource();

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    sourceRef.current = source;
    currentBufferRef.current = buffer;
    startedAtRef.current = ctx.currentTime - offset;
    pausedAtRef.current = 0;

    source.start(0, offset);
    return source;
  }, [getCtx, stopSource]);

  // Core playback logic
  useEffect(() => {
    speakNextRef.current = async (idx: number) => {
      if (stoppedRef.current) return;

      if (idx >= paragraphsRef.current.length) {
        cleanup();
        setPlaying(false);
        setCurrentIdx(-1);
        setLoading(false);
        const cb = onCompleteRef.current;
        onCompleteRef.current = null;
        if (cb) cb();
        return;
      }

      setCurrentIdx(idx);

      // Prefetch current + upcoming
      for (let i = idx; i < Math.min(idx + PREFETCH_AHEAD + 1, paragraphsRef.current.length); i++) {
        prefetch(i);
      }

      setLoading(true);

      try {
        const buffer = await cacheRef.current.get(idx);
        if (stoppedRef.current || !buffer) return;

        setLoading(false);

        // Evict old cache entries
        for (const key of cacheRef.current.keys()) {
          if (key < idx) cacheRef.current.delete(key);
        }

        const source = playBuffer(buffer);

        source.onended = () => {
          // Only advance if not paused/stopped (onended also fires on stop())
          if (!stoppedRef.current && !pausedAtRef.current) {
            speakNextRef.current?.(idx + 1);
          }
        };
      } catch {
        // Skip failed paragraph
        if (!stoppedRef.current && idx < paragraphsRef.current.length - 1) {
          cacheRef.current.delete(idx);
          speakNextRef.current?.(idx + 1);
        } else {
          cleanup();
          setPlaying(false);
          setCurrentIdx(-1);
          setLoading(false);
        }
      }
    };
  }, [cleanup, prefetch, playBuffer]);

  const play = useCallback(
    (texts: string[], startIdx = 0) => {
      cleanup();
      stoppedRef.current = false;
      paragraphsRef.current = texts;
      setPlaying(true);
      setPaused(false);
      speakNextRef.current?.(startIdx);
    },
    [cleanup]
  );

  const pause = useCallback(() => {
    const ctx = ctxRef.current;
    if (ctx && sourceRef.current) {
      pausedAtRef.current = ctx.currentTime - startedAtRef.current;
      stopSource();
      setPaused(true);
    }
  }, [stopSource]);

  const resume = useCallback(() => {
    if (currentBufferRef.current && pausedAtRef.current) {
      const source = playBuffer(currentBufferRef.current, pausedAtRef.current);
      const idx = currentIdx;
      source.onended = () => {
        if (!stoppedRef.current && !pausedAtRef.current) {
          speakNextRef.current?.(idx + 1);
        }
      };
      setPaused(false);
    }
  }, [playBuffer, currentIdx]);

  const stop = useCallback(() => {
    stoppedRef.current = true;
    cleanup();
    setPlaying(false);
    setPaused(false);
    setCurrentIdx(-1);
    setLoading(false);
    paragraphsRef.current = [];
  }, [cleanup]);

  const setRate = useCallback((newRate: number) => {
    rateRef.current = newRate;
    setRateState(newRate);
  }, []);

  const setOnChapterComplete = useCallback((cb: () => void) => {
    onCompleteRef.current = cb;
  }, []);

  return {
    playing,
    paused,
    loading,
    currentIdx,
    rate,
    play,
    pause,
    resume,
    stop,
    setRate,
    setOnChapterComplete,
  };
}
