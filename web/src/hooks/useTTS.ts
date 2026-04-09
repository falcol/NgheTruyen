"use client";

import { useState, useCallback, useRef } from "react";

export function useTTS() {
  const [playing, setPlaying] = useState(false);
  const [paused, setPaused] = useState(false);
  const [currentIdx, setCurrentIdx] = useState(-1);
  const [rate, setRateState] = useState(1);
  const [onComplete, setOnComplete] = useState<(() => void) | null>(null);

  const paragraphsRef = useRef<string[]>([]);
  const rateRef = useRef(1);

  const speakNext = useCallback(
    (idx: number) => {
      if (idx >= paragraphsRef.current.length) {
        setPlaying(false);
        setCurrentIdx(-1);
        setOnComplete((prev) => {
          if (prev) prev();
          return null;
        });
        return;
      }

      setCurrentIdx(idx);

      const u = new SpeechSynthesisUtterance(paragraphsRef.current[idx]);
      u.lang = "vi-VN";
      u.rate = rateRef.current;

      u.onend = () => speakNext(idx + 1);
      u.onerror = () => {
        setPlaying(false);
        setCurrentIdx(-1);
      };

      window.speechSynthesis.speak(u);
    },
    []
  );

  const play = useCallback(
    (texts: string[], startIdx = 0) => {
      window.speechSynthesis.cancel();
      paragraphsRef.current = texts;
      setPlaying(true);
      setPaused(false);
      speakNext(startIdx);
    },
    [speakNext]
  );

  const pause = useCallback(() => {
    window.speechSynthesis.pause();
    setPaused(true);
  }, []);

  const resume = useCallback(() => {
    window.speechSynthesis.resume();
    setPaused(false);
  }, []);

  const stop = useCallback(() => {
    window.speechSynthesis.cancel();
    setPlaying(false);
    setPaused(false);
    setCurrentIdx(-1);
    paragraphsRef.current = [];
  }, []);

  const setRate = useCallback((newRate: number) => {
    rateRef.current = newRate;
    setRateState(newRate);
  }, []);

  const setOnChapterComplete = useCallback((cb: () => void) => {
    setOnComplete(() => cb);
  }, []);

  return {
    playing,
    paused,
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
