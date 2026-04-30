"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { buildTTSChunks, type TTSChunk } from "@/lib/tts-chunks";

const VOICE_STORAGE_KEY = "nghetruyen-tts-voice";

function getVietnameseVoices(): SpeechSynthesisVoice[] {
  if (typeof window === "undefined" || !window.speechSynthesis) return [];

  const voices = window.speechSynthesis.getVoices();
  const viVoices = voices.filter((v) => v.lang === "vi-VN");
  if (viVoices.length > 0) return viVoices;

  return voices.filter((v) => v.lang.startsWith("vi"));
}

function getSavedVoiceName(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(VOICE_STORAGE_KEY);
}

function selectVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  if (voices.length === 0) return null;

  const savedName = getSavedVoiceName();
  if (savedName) {
    const saved = voices.find((v) => v.name === savedName);
    if (saved) return saved;
  }

  const google = voices.find((v) => v.name.includes("Google"));
  if (google) return google;

  const ms = voices.find((v) => v.name.includes("Microsoft"));
  if (ms) return ms;

  return voices[0];
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
  const [viVoices, setViVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [selectedVoiceName, setSelectedVoiceName] = useState<string | null>(null);

  const rateRef = useRef(1);
  const stoppedRef = useRef(false);
  const playIdRef = useRef(0);
  const onCompleteRef = useRef<(() => void) | null>(null);
  const chunksRef = useRef<TTSChunk[]>([]);
  const currentChunkIdxRef = useRef(-1);
  const preparedKeyRef = useRef<string | null>(null);
  const preparedRateRef = useRef(1);
  const voiceRef = useRef<SpeechSynthesisVoice | null>(null);
  const playChunkAtRef = useRef<
    (idx: number, playId: number) => void
  >(() => {});

  const refreshVoices = useCallback(() => {
    const voices = getVietnameseVoices();
    setViVoices(voices);
    const chosen = selectVoice(voices);
    voiceRef.current = chosen;
    if (chosen) setSelectedVoiceName(chosen.name);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined" || !window.speechSynthesis) return;

    refreshVoices();
    window.speechSynthesis.addEventListener("voiceschanged", refreshVoices);
    return () => {
      window.speechSynthesis.removeEventListener("voiceschanged", refreshVoices);
    };
  }, [refreshVoices]);

  const playChunkAt = useCallback((idx: number, playId: number) => {
    if (playIdRef.current !== playId || stoppedRef.current) return;

    if (idx >= chunksRef.current.length) {
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

    const utterance = new SpeechSynthesisUtterance(chunk.text);
    utterance.voice = voiceRef.current;
    utterance.lang = "vi-VN";
    utterance.rate = rateRef.current;
    utterance.pitch = 1;

    utterance.onstart = () => {
      setLoading(false);
    };

    utterance.onend = () => {
      if (playIdRef.current !== playId || stoppedRef.current) return;
      playChunkAtRef.current(idx + 1, playId);
    };

    utterance.onerror = (e) => {
      if (
        e.error === "canceled" ||
        playIdRef.current !== playId ||
        stoppedRef.current
      )
        return;
      playChunkAtRef.current(idx + 1, playId);
    };

    window.speechSynthesis.speak(utterance);
  }, []);

  useEffect(() => {
    playChunkAtRef.current = playChunkAt;
  }, [playChunkAt]);

  const prepare = useCallback(
    (key: string, paragraphs: string[]) => {
      if (!paragraphs.length) return;
      if (
        preparedKeyRef.current === key &&
        preparedRateRef.current === rateRef.current
      ) {
        return;
      }

      stoppedRef.current = false;
      window.speechSynthesis.cancel();
      chunksRef.current = buildTTSChunks(paragraphs);
      currentChunkIdxRef.current = -1;
      preparedKeyRef.current = key;
      preparedRateRef.current = rateRef.current;
      setTotalChunks(chunksRef.current.length);
    },
    [],
  );

  const play = useCallback(
    (key: string, paragraphs: string[]) => {
      if (!paragraphs.length) return;
      if (typeof window === "undefined" || !window.speechSynthesis) return;

      stoppedRef.current = false;
      const newPlayId = ++playIdRef.current;

      window.speechSynthesis.cancel();

      const hasPrepared =
        preparedKeyRef.current === key &&
        preparedRateRef.current === rateRef.current &&
        chunksRef.current.length > 0;

      if (!hasPrepared) {
        chunksRef.current = buildTTSChunks(paragraphs);
        preparedKeyRef.current = key;
        preparedRateRef.current = rateRef.current;
      }

      currentChunkIdxRef.current = -1;

      setPlaying(true);
      setPaused(false);
      setLoading(true);
      setTotalChunks(chunksRef.current.length);

      playChunkAt(0, newPlayId);
    },
    [playChunkAt],
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
    stoppedRef.current = true;
    window.speechSynthesis.cancel();
    chunksRef.current = [];
    currentChunkIdxRef.current = -1;
    preparedKeyRef.current = null;
    preparedRateRef.current = rateRef.current;
    setPlaying(false);
    setPaused(false);
    setLoading(false);
    setCurrentIdx(-1);
    setActiveRange(null);
    setTotalChunks(0);
  }, []);

  const skipForward = useCallback(() => {
    if (currentChunkIdxRef.current < 0) return;
    const newPlayId = ++playIdRef.current;
    const nextIdx = currentChunkIdxRef.current + 1;
    if (nextIdx >= chunksRef.current.length) return;
    window.speechSynthesis.cancel();
    playChunkAt(nextIdx, newPlayId);
  }, [playChunkAt]);

  const skipBackward = useCallback(() => {
    if (currentChunkIdxRef.current < 0) return;
    const newPlayId = ++playIdRef.current;
    const targetIdx = Math.max(0, currentChunkIdxRef.current - 1);
    window.speechSynthesis.cancel();
    playChunkAt(targetIdx, newPlayId);
  }, [playChunkAt]);

  const setRate = useCallback((newRate: number) => {
    if (rateRef.current === newRate) return;
    rateRef.current = newRate;
    window.speechSynthesis.cancel();
    chunksRef.current = [];
    currentChunkIdxRef.current = -1;
    preparedKeyRef.current = null;
    preparedRateRef.current = newRate;
    setRateState(newRate);
    setPlaying(false);
    setPaused(false);
    setLoading(false);
    setCurrentIdx(-1);
    setActiveRange(null);
  }, []);

  const setVoice = useCallback((voiceName: string) => {
    const voices = getVietnameseVoices();
    const found = voices.find((v) => v.name === voiceName);
    if (!found) return;

    voiceRef.current = found;
    setSelectedVoiceName(voiceName);
    localStorage.setItem(VOICE_STORAGE_KEY, voiceName);

    // Reset playback with new voice
    window.speechSynthesis.cancel();
    chunksRef.current = [];
    currentChunkIdxRef.current = -1;
    preparedKeyRef.current = null;
    setPlaying(false);
    setPaused(false);
    setLoading(false);
    setCurrentIdx(-1);
    setActiveRange(null);
  }, []);

  const setOnChapterComplete = useCallback((cb: () => void) => {
    onCompleteRef.current = cb;
  }, []);

  useEffect(() => {
    return () => {
      stoppedRef.current = true;
      if (typeof window !== "undefined" && window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  return {
    playing,
    paused,
    loading,
    currentIdx,
    activeRange,
    rate,
    totalChunks,
    currentChunkIdx: currentChunkIdxRef.current,
    viVoices,
    selectedVoiceName,
    play,
    prepare,
    pause,
    resume,
    stop,
    skipForward,
    skipBackward,
    setRate,
    setVoice,
    setOnChapterComplete,
  };
}
