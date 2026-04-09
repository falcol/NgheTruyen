"use client";

import { useState, useCallback, useRef, useEffect } from "react";

export function useTTS() {
  const [playing, setPlaying] = useState(false);
  const [paused, setPaused] = useState(false);
  const [currentIdx, setCurrentIdx] = useState(-1);
  const [rate, setRateState] = useState(1);
  const [onComplete, setOnComplete] = useState<(() => void) | null>(null);

  // Voice management
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [selectedVoice, setSelectedVoice] =
    useState<SpeechSynthesisVoice | null>(null);

  const paragraphsRef = useRef<string[]>([]);
  const rateRef = useRef(1);
  const voiceRef = useRef<SpeechSynthesisVoice | null>(null);

  // Load available Vietnamese voices, auto-pick best female voice
  useEffect(() => {
    const STORAGE_KEY = "tts-voice-name";

    const pickBestVoice = (viVoices: SpeechSynthesisVoice[]) => {
      // 1. Restore saved preference
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const found = viVoices.find((v) => v.name === saved);
        if (found) return found;
      }

      // 2. Prefer female/natural Vietnamese voices (priority order)
      const prefer = [
        "Google Tiếng Việt",    // Chrome — good quality
        "Microsoft An Online",  // Edge — natural female
        "Microsoft An",         // Windows local
        "vi-VN",                // Any labeled vi-VN
      ];
      for (const name of prefer) {
        const found = viVoices.find((v) => v.name.includes(name));
        if (found) return found;
      }

      // 3. First available
      return viVoices[0];
    };

    const loadVoices = () => {
      const all = window.speechSynthesis.getVoices();
      const viVoices = all.filter((v) => v.lang.startsWith("vi"));
      setVoices(viVoices);

      if (!voiceRef.current && viVoices.length > 0) {
        const best = pickBestVoice(viVoices);
        voiceRef.current = best;
        setSelectedVoice(best);
      }
    };

    loadVoices();
    window.speechSynthesis.addEventListener("voiceschanged", loadVoices);
    return () =>
      window.speechSynthesis.removeEventListener("voiceschanged", loadVoices);
  }, []);

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
      if (voiceRef.current) u.voice = voiceRef.current;

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

  const setVoice = useCallback((voice: SpeechSynthesisVoice) => {
    voiceRef.current = voice;
    setSelectedVoice(voice);
    localStorage.setItem("tts-voice-name", voice.name);
  }, []);

  const setOnChapterComplete = useCallback((cb: () => void) => {
    setOnComplete(() => cb);
  }, []);

  return {
    playing,
    paused,
    currentIdx,
    rate,
    voices,
    selectedVoice,
    play,
    pause,
    resume,
    stop,
    setRate,
    setVoice,
    setOnChapterComplete,
  };
}
