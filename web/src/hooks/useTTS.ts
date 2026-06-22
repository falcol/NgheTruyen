"use client";

import { useReducer, useState, useCallback, useRef, useEffect } from "react";
import { buildTTSChunks, findChunkIndexForParagraph, type TTSChunk } from "@/lib/tts-chunks";

const VOICE_STORAGE_KEY = "nghetruyen-tts-voice";

// ---------------------------------------------------------------------------
// Reducer – batches related state updates into single re-renders
// ---------------------------------------------------------------------------

interface TTSPlaybackState {
  playing: boolean;
  paused: boolean;
  loading: boolean;
  currentIdx: number;
  activeRange: { start: number; end: number } | null;
  totalChunks: number;
}

type TTSAction =
  | { type: "START"; totalChunks: number }
  | { type: "CHUNK_START"; currentIdx: number; activeRange: { start: number; end: number } }
  | { type: "UTTERANCE_START" }
  | { type: "PAUSE" }
  | { type: "RESUME" }
  | { type: "STOP" }
  | { type: "COMPLETE" }
  | { type: "SET_TOTAL_CHUNKS"; totalChunks: number };

const INITIAL_PLAYBACK: TTSPlaybackState = {
  playing: false,
  paused: false,
  loading: false,
  currentIdx: -1,
  activeRange: null,
  totalChunks: 0,
};

function ttsReducer(state: TTSPlaybackState, action: TTSAction): TTSPlaybackState {
  switch (action.type) {
    case "START":
      return { ...state, playing: true, paused: false, loading: true, totalChunks: action.totalChunks };
    case "CHUNK_START":
      return { ...state, currentIdx: action.currentIdx, activeRange: action.activeRange };
    case "UTTERANCE_START":
      return state.loading ? { ...state, loading: false } : state;
    case "PAUSE":
      return { ...state, paused: true };
    case "RESUME":
      return { ...state, paused: false };
    case "STOP":
      return INITIAL_PLAYBACK;
    case "COMPLETE":
      return { ...INITIAL_PLAYBACK, totalChunks: state.totalChunks };
    case "SET_TOTAL_CHUNKS":
      return state.totalChunks === action.totalChunks ? state : { ...state, totalChunks: action.totalChunks };
    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useTTS() {
  const [state, dispatch] = useReducer(ttsReducer, INITIAL_PLAYBACK);
  const [rate, setRateState] = useState(1);
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
  // Chrome/Android Web Speech API stops after ~15s when tab loses focus.
  // Workaround from Read Aloud (MIT): periodically pause+resume to reset timer.
  const keepAliveRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const startKeepAlive = useCallback(() => {
    if (keepAliveRef.current) return;
    keepAliveRef.current = setInterval(() => {
      const ss = window.speechSynthesis;
      if (ss.speaking && !ss.paused) {
        ss.pause();
        ss.resume();
      }
    }, 10_000);
  }, []);

  const stopKeepAlive = useCallback(() => {
    if (keepAliveRef.current) {
      clearInterval(keepAliveRef.current);
      keepAliveRef.current = null;
    }
  }, []);

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
      // Stop keep-alive via ref to avoid adding stopKeepAlive to callback deps
      if (keepAliveRef.current) {
        clearInterval(keepAliveRef.current);
        keepAliveRef.current = null;
      }
      dispatch({ type: "COMPLETE" });
      currentChunkIdxRef.current = -1;
      const cb = onCompleteRef.current;
      onCompleteRef.current = null;
      if (cb) cb();
      return;
    }

    currentChunkIdxRef.current = idx;
    const chunk = chunksRef.current[idx];

    dispatch({
      type: "CHUNK_START",
      currentIdx: chunk.startParagraphIdx,
      activeRange: { start: chunk.startParagraphIdx, end: chunk.endParagraphIdx },
    });

    const utterance = new SpeechSynthesisUtterance(chunk.text);
    utterance.voice = voiceRef.current;
    utterance.lang = "vi-VN";
    utterance.rate = rateRef.current;
    utterance.pitch = 1;

    utterance.onstart = () => {
      dispatch({ type: "UTTERANCE_START" });
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
      dispatch({ type: "SET_TOTAL_CHUNKS", totalChunks: chunksRef.current.length });
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
      dispatch({ type: "START", totalChunks: chunksRef.current.length });

      startKeepAlive();
      playChunkAt(0, newPlayId);
    },
    [playChunkAt, startKeepAlive],
  );

  // Begin playback at the chunk containing `startParagraphIdx` (e.g. the paragraph
  // currently in the viewport). Mirrors `play` but seeds the start chunk.
  const playFromParagraph = useCallback(
    (key: string, paragraphs: string[], startParagraphIdx: number) => {
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

      let startChunk = findChunkIndexForParagraph(chunksRef.current, startParagraphIdx);
      if (startChunk < 0) startChunk = 0;

      currentChunkIdxRef.current = startChunk;
      dispatch({ type: "START", totalChunks: chunksRef.current.length });

      startKeepAlive();
      playChunkAt(startChunk, newPlayId);
    },
    [playChunkAt, startKeepAlive],
  );

  const pause = useCallback(() => {
    window.speechSynthesis.pause();
    dispatch({ type: "PAUSE" });
  }, []);

  const resume = useCallback(() => {
    window.speechSynthesis.resume();
    dispatch({ type: "RESUME" });
  }, []);

  const stop = useCallback(() => {
    stopKeepAlive();
    stoppedRef.current = true;
    window.speechSynthesis.cancel();
    chunksRef.current = [];
    currentChunkIdxRef.current = -1;
    preparedKeyRef.current = null;
    preparedRateRef.current = rateRef.current;
    dispatch({ type: "STOP" });
  }, [stopKeepAlive]);

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
    dispatch({ type: "COMPLETE" });
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
    dispatch({ type: "COMPLETE" });
  }, []);

  const setOnChapterComplete = useCallback((cb: () => void) => {
    onCompleteRef.current = cb;
  }, []);

  useEffect(() => {
    return () => {
      stopKeepAlive();
      stoppedRef.current = true;
      if (typeof window !== "undefined" && window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, [stopKeepAlive]);

  return {
    playing: state.playing,
    paused: state.paused,
    loading: state.loading,
    currentIdx: state.currentIdx,
    activeRange: state.activeRange,
    rate,
    totalChunks: state.totalChunks,
    currentChunkIdx: currentChunkIdxRef.current,
    viVoices,
    selectedVoiceName,
    play,
    playFromParagraph,
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
