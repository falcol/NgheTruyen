"use client";

import { useReducer, useState, useCallback, useRef, useEffect } from "react";
import {
  buildTTSChunks,
  findChunkIndexForParagraph,
  type TTSChunk,
} from "@/lib/tts-chunks";
import {
  DEFAULT_EDGE_VOICE,
  EDGE_VI_VOICES,
  type EdgeTTSVoice,
} from "@/lib/tts-voices";

const VOICE_STORAGE_KEY = "nghetruyen-tts-voice";
/** Warm ahead while playing — Read Aloud prefetches next; keep pipeline short so chunk 0 wins Edge slots */
const PREFETCH_AHEAD = 3;
const WARM_ON_PREPARE = 3;
const MAX_BLOB_CACHE = 64;
const CLIENT_FETCH_RETRIES = 2;
/**
 * Window where we may swap if secondary is ready.
 * timeupdate alone is ~4Hz (~250ms) — pair with a tight poll for Read Aloud-like joins.
 */
const HANDOFF_WINDOW_S = 0.55;
/**
 * Swap this many seconds before reported duration end.
 * Edge MP3 chunks usually carry ~150–250ms encoder padding/silence at the tail;
 * cutting there joins speech-to-speech closer to Read Aloud (avoids audible hole).
 */
const HANDOFF_SWITCH_S = 0.22;
const HANDOFF_POLL_MS = 40;

// ---------------------------------------------------------------------------
// Reducer
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
      return {
        ...state,
        playing: true,
        paused: false,
        loading: true,
        totalChunks: action.totalChunks,
      };
    case "CHUNK_START":
      return {
        ...state,
        currentIdx: action.currentIdx,
        activeRange: action.activeRange,
      };
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
      return state.totalChunks === action.totalChunks
        ? state
        : { ...state, totalChunks: action.totalChunks };
    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Client audio cache + fetch
// ---------------------------------------------------------------------------

function getSavedVoiceName(): string {
  if (typeof window === "undefined") return DEFAULT_EDGE_VOICE;
  const saved = localStorage.getItem(VOICE_STORAGE_KEY);
  if (saved && EDGE_VI_VOICES.some((v) => v.name === saved)) return saved;
  return DEFAULT_EDGE_VOICE;
}

function cacheKey(text: string, voice: string): string {
  return `${voice}\0${text}`;
}

function createAudioEl(): HTMLAudioElement {
  const el = new Audio();
  el.preload = "auto";
  const media = el as HTMLMediaElement & {
    preservesPitch?: boolean;
    mozPreservesPitch?: boolean;
  };
  media.preservesPitch = true;
  media.mozPreservesPitch = true;
  return el;
}

async function fetchChunkAudio(text: string, voice: string): Promise<Blob> {
  let lastErr: unknown;
  for (let attempt = 1; attempt <= CLIENT_FETCH_RETRIES; attempt++) {
    try {
      const res = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice }),
      });
      if (!res.ok) {
        const msg = await res.text().catch(() => res.statusText);
        throw new Error(`TTS ${res.status}: ${msg}`);
      }
      const blob = await res.blob();
      if (blob.size < 64) throw new Error("TTS empty blob");
      return blob;
    } catch (err) {
      lastErr = err;
      if (attempt < CLIENT_FETCH_RETRIES) {
        await new Promise((r) => setTimeout(r, 180 * attempt));
      }
    }
  }
  throw lastErr instanceof Error ? lastErr : new Error("TTS fetch failed");
}

/**
 * Wait until media is buffered enough to start.
 * preferEnough=true waits for HAVE_ENOUGH_DATA (canplaythrough) so handoff play() does not stall.
 */
function waitCanPlay(
  audio: HTMLAudioElement,
  timeoutMs = 20_000,
  preferEnough = false,
): Promise<void> {
  const need = preferEnough
    ? HTMLMediaElement.HAVE_ENOUGH_DATA
    : HTMLMediaElement.HAVE_FUTURE_DATA;
  if (audio.readyState >= need) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const t = window.setTimeout(() => {
      cleanup();
      // Secondary: accept FUTURE_DATA if ENOUGH never arrives (slow blob)
      if (preferEnough && audio.readyState >= HTMLMediaElement.HAVE_FUTURE_DATA) {
        resolve();
        return;
      }
      reject(new Error("audio canplay timeout"));
    }, timeoutMs);
    const onReady = () => {
      if (audio.readyState < need && preferEnough) return;
      cleanup();
      resolve();
    };
    const onError = () => {
      cleanup();
      reject(new Error("audio load error"));
    };
    const cleanup = () => {
      window.clearTimeout(t);
      audio.removeEventListener("canplay", onReady);
      audio.removeEventListener("canplaythrough", onReady);
      audio.removeEventListener("error", onError);
    };
    audio.addEventListener("canplay", onReady);
    audio.addEventListener("canplaythrough", onReady);
    audio.addEventListener("error", onError);
  });
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useTTS() {
  const [state, dispatch] = useReducer(ttsReducer, INITIAL_PLAYBACK);
  const [rate, setRateState] = useState(1);
  const [viVoices] = useState<EdgeTTSVoice[]>(EDGE_VI_VOICES);
  const [selectedVoiceName, setSelectedVoiceName] = useState<string>(
    DEFAULT_EDGE_VOICE,
  );

  const rateRef = useRef(1);
  const voiceRef = useRef(DEFAULT_EDGE_VOICE);
  const stoppedRef = useRef(false);
  const playIdRef = useRef(0);
  const onCompleteRef = useRef<(() => void) | null>(null);
  const chunksRef = useRef<TTSChunk[]>([]);
  const currentChunkIdxRef = useRef(-1);
  const preparedKeyRef = useRef<string | null>(null);

  // Dual buffer: while A plays, B preloads next → near-gapless handoff
  const primaryRef = useRef<HTMLAudioElement | null>(null);
  const secondaryRef = useRef<HTMLAudioElement | null>(null);
  /** Chunk index currently loaded into secondary (or -1) */
  const secondaryChunkRef = useRef(-1);
  const handoffArmedRef = useRef(false);
  /** setInterval id for precise end-of-chunk handoff (timeupdate is too coarse) */
  const handoffWatchRef = useRef<number | null>(null);

  const blobCacheRef = useRef<Map<string, string>>(new Map());
  const inflightRef = useRef<Map<string, Promise<string>>>(new Map());

  const playChunkAtRef = useRef<(idx: number, playId: number) => void>(() => {});
  const playPrimedChunkRef = useRef<
    (
      idx: number,
      playId: number,
      audio: HTMLAudioElement,
      pauseWhenPlaying?: HTMLAudioElement,
      alreadyPlaying?: boolean,
    ) => void
  >(() => {});
  const handoffToNextRef = useRef<(fromIdx: number, playId: number) => void>(
    () => {},
  );

  useEffect(() => {
    const saved = getSavedVoiceName();
    voiceRef.current = saved;
    setSelectedVoiceName(saved);
  }, []);

  const getPrimary = useCallback((): HTMLAudioElement => {
    if (!primaryRef.current) primaryRef.current = createAudioEl();
    return primaryRef.current;
  }, []);

  const getSecondary = useCallback((): HTMLAudioElement => {
    if (!secondaryRef.current) secondaryRef.current = createAudioEl();
    return secondaryRef.current;
  }, []);

  const revokeAllBlobs = useCallback(() => {
    for (const url of blobCacheRef.current.values()) {
      URL.revokeObjectURL(url);
    }
    blobCacheRef.current.clear();
    inflightRef.current.clear();
  }, []);

  const trimCache = useCallback(() => {
    const map = blobCacheRef.current;
    while (map.size > MAX_BLOB_CACHE) {
      const first = map.keys().next().value as string | undefined;
      if (first === undefined) break;
      const url = map.get(first);
      if (url) URL.revokeObjectURL(url);
      map.delete(first);
    }
  }, []);

  const ensureChunkUrl = useCallback(
    async (text: string, voice: string): Promise<string> => {
      const key = cacheKey(text, voice);
      const cached = blobCacheRef.current.get(key);
      if (cached) return cached;

      const inflight = inflightRef.current.get(key);
      if (inflight) return inflight;

      const promise = fetchChunkAudio(text, voice)
        .then((blob) => {
          const url = URL.createObjectURL(blob);
          blobCacheRef.current.set(key, url);
          inflightRef.current.delete(key);
          trimCache();
          return url;
        })
        .catch((err) => {
          inflightRef.current.delete(key);
          throw err;
        });

      inflightRef.current.set(key, promise);
      return promise;
    },
    [trimCache],
  );

  const prefetchAround = useCallback(
    (fromIdx: number, playId: number) => {
      const voice = voiceRef.current;
      const chunks = chunksRef.current;
      for (let i = fromIdx; i <= fromIdx + PREFETCH_AHEAD && i < chunks.length; i++) {
        if (playIdRef.current !== playId || stoppedRef.current) return;
        const text = chunks[i].text;
        const key = cacheKey(text, voice);
        if (blobCacheRef.current.has(key) || inflightRef.current.has(key)) continue;
        void ensureChunkUrl(text, voice).catch(() => {});
      }
    },
    [ensureChunkUrl],
  );

  const clearAudioHandlers = useCallback((audio: HTMLAudioElement) => {
    audio.onended = null;
    audio.onerror = null;
    audio.onplaying = null;
    audio.ontimeupdate = null;
  }, []);

  const clearHandoffWatch = useCallback(() => {
    if (handoffWatchRef.current != null) {
      window.clearInterval(handoffWatchRef.current);
      window.clearTimeout(handoffWatchRef.current);
      handoffWatchRef.current = null;
    }
  }, []);

  const stopAudio = useCallback(() => {
    clearHandoffWatch();
    handoffArmedRef.current = false;
    secondaryChunkRef.current = -1;
    for (const ref of [primaryRef, secondaryRef]) {
      const audio = ref.current;
      if (!audio) continue;
      clearAudioHandlers(audio);
      audio.pause();
      audio.removeAttribute("src");
      try {
        audio.load();
      } catch {
        /* ignore */
      }
    }
  }, [clearAudioHandlers, clearHandoffWatch]);

  /** Load next chunk into secondary buffer while primary is playing. */
  const armSecondary = useCallback(
    async (nextIdx: number, playId: number) => {
      if (nextIdx >= chunksRef.current.length) {
        secondaryChunkRef.current = -1;
        return;
      }
      if (playIdRef.current !== playId || stoppedRef.current) return;

      const chunk = chunksRef.current[nextIdx];
      let url: string;
      try {
        url = await ensureChunkUrl(chunk.text, voiceRef.current);
      } catch {
        return;
      }
      if (playIdRef.current !== playId || stoppedRef.current) return;

      const sec = getSecondary();
      clearAudioHandlers(sec);
      if (sec.src !== url) {
        sec.src = url;
        sec.playbackRate = rateRef.current;
        try {
          sec.load();
        } catch {
          /* ignore */
        }
      } else {
        sec.playbackRate = rateRef.current;
      }
      secondaryChunkRef.current = nextIdx;
      try {
        await waitCanPlay(sec, 20_000, true);
        // Ensure start position while there is still time to rebuffer (not at handoff)
        if (sec.currentTime > 0.05) {
          try {
            sec.currentTime = 0;
            await waitCanPlay(sec, 20_000, true);
          } catch {
            /* still try play later */
          }
        }
      } catch {
        /* still try play later */
      }
    },
    [clearAudioHandlers, ensureChunkUrl, getSecondary],
  );

  const finishPlayback = useCallback(() => {
    stopAudio();
    dispatch({ type: "COMPLETE" });
    currentChunkIdxRef.current = -1;
    const cb = onCompleteRef.current;
    onCompleteRef.current = null;
    if (cb) cb();
  }, [stopAudio]);

  /**
   * Instant handoff: secondary already has next chunk → swap roles and play.
   * Falls back to full load path if buffer not ready.
   * Starts next before silencing old to shrink the join gap (Read Aloud-style).
   */
  const handoffToNext = useCallback(
    (fromIdx: number, playId: number) => {
      if (playIdRef.current !== playId || stoppedRef.current) return;
      clearHandoffWatch();
      handoffArmedRef.current = false;

      const nextIdx = fromIdx + 1;
      if (nextIdx >= chunksRef.current.length) {
        finishPlayback();
        return;
      }

      // Fast path: secondary is already primed for nextIdx
      if (
        secondaryChunkRef.current === nextIdx &&
        secondaryRef.current &&
        secondaryRef.current.src
      ) {
        const oldPrimary = getPrimary();
        const newPrimary = getSecondary();
        clearAudioHandlers(oldPrimary);

        primaryRef.current = newPrimary;
        secondaryRef.current = oldPrimary;
        secondaryChunkRef.current = -1;

        playPrimedChunkRef.current(nextIdx, playId, newPrimary, oldPrimary, false);
        return;
      }

      playChunkAtRef.current(nextIdx, playId);
    },
    [clearAudioHandlers, clearHandoffWatch, finishPlayback, getPrimary, getSecondary],
  );

  const playPrimedChunk = useCallback(
    async (
      idx: number,
      playId: number,
      audio: HTMLAudioElement,
      pauseWhenPlaying?: HTMLAudioElement,
      alreadyPlaying = false,
    ) => {
      if (playIdRef.current !== playId || stoppedRef.current) return;

      currentChunkIdxRef.current = idx;
      const chunk = chunksRef.current[idx];

      // Minimal work before play() — UI/prefetch after audio is kicked (Read Aloud-style)
      clearHandoffWatch();
      handoffArmedRef.current = false;
      if (!alreadyPlaying) {
        clearAudioHandlers(audio);
      }
      audio.playbackRate = rateRef.current;

      let other = pauseWhenPlaying ?? null;
      const silenceOther = () => {
        if (!other) return;
        try {
          other.pause();
        } catch {
          /* ignore */
        }
        other = null;
      };

      audio.onplaying = () => {
        if (playIdRef.current !== playId || stoppedRef.current) return;
        silenceOther();
        dispatch({ type: "UTTERANCE_START" });
      };

      audio.onended = () => {
        if (playIdRef.current !== playId || stoppedRef.current) return;
        clearHandoffWatch();
        handoffToNextRef.current(idx, playId);
      };

      audio.onerror = () => {
        if (playIdRef.current !== playId || stoppedRef.current) return;
        clearHandoffWatch();
        playChunkAtRef.current(idx + 1, playId);
      };

      // Early handoff near end — precise timeout + poll fallback
      const tryEarlyHandoff = () => {
        if (playIdRef.current !== playId || stoppedRef.current) return;
        if (handoffArmedRef.current) return;
        if (audio.paused) return;

        const d = audio.duration;
        if (!Number.isFinite(d) || d <= 0) return;
        const rate = audio.playbackRate > 0 ? audio.playbackRate : 1;
        const remaining = (d - audio.currentTime) / rate;
        if (remaining > HANDOFF_WINDOW_S) return;

        const nextIdx = idx + 1;
        if (nextIdx >= chunksRef.current.length) return;

        const next = secondaryRef.current;
        // HAVE_ENOUGH_DATA: avoid play() stall if only metadata is ready
        if (
          secondaryChunkRef.current !== nextIdx ||
          !next?.src ||
          next.readyState < HTMLMediaElement.HAVE_ENOUGH_DATA
        ) {
          // Keep polling until secondary is ready — do not lock armed early
          return;
        }
        // Swap only in the final moments to avoid double-speak
        if (remaining > HANDOFF_SWITCH_S) return;

        handoffArmedRef.current = true;
        clearHandoffWatch();

        // Instant swap: play next in THIS turn, then wire handlers (skip second play())
        // Do NOT seek — seek before play rebuffers and adds ~100ms+ gap.
        next.playbackRate = rateRef.current;
        clearAudioHandlers(audio);
        primaryRef.current = next;
        secondaryRef.current = audio;
        secondaryChunkRef.current = -1;

        void next.play().catch(() => {
          /* playPrimedChunk will retry via alreadyPlaying=false path if needed */
        });
        // Silence previous immediately after play() is invoked (same task when possible)
        try {
          audio.pause();
        } catch {
          /* ignore */
        }

        playPrimedChunkRef.current(nextIdx, playId, next, undefined, true);
      };

      const scheduleHandoffWatch = () => {
        clearHandoffWatch();
        const d = audio.duration;
        if (Number.isFinite(d) && d > 0) {
          const rate = audio.playbackRate > 0 ? audio.playbackRate : 1;
          const delayMs = Math.max(
            0,
            ((d - audio.currentTime) / rate - HANDOFF_SWITCH_S) * 1000,
          );
          // One-shot timer aimed at the switch point (more reliable than 4Hz timeupdate)
          const timeoutId = window.setTimeout(() => {
            tryEarlyHandoff();
            // If secondary was late, fall back to tight poll until end
            if (!handoffArmedRef.current && playIdRef.current === playId) {
              handoffWatchRef.current = window.setInterval(
                tryEarlyHandoff,
                HANDOFF_POLL_MS,
              );
            }
          }, delayMs);
          handoffWatchRef.current = timeoutId;
        } else {
          handoffWatchRef.current = window.setInterval(
            tryEarlyHandoff,
            HANDOFF_POLL_MS,
          );
        }
      };

      audio.ontimeupdate = tryEarlyHandoff;
      scheduleHandoffWatch();

      // Non-critical UI + pipeline
      dispatch({
        type: "CHUNK_START",
        currentIdx: chunk.startParagraphIdx,
        activeRange: {
          start: chunk.startParagraphIdx,
          end: chunk.endParagraphIdx,
        },
      });
      prefetchAround(idx, playId);
      void armSecondary(idx + 1, playId);

      if (alreadyPlaying) {
        silenceOther();
        if (playIdRef.current === playId && !stoppedRef.current) {
          dispatch({ type: "UTTERANCE_START" });
        }
        // Re-arm timer for THIS chunk's end
        scheduleHandoffWatch();
        return;
      }

      try {
        const playP = audio.play();
        queueMicrotask(silenceOther);
        await playP;
        silenceOther();
        // Duration may only be known after play — reschedule precise handoff
        scheduleHandoffWatch();
        if (playIdRef.current === playId && !stoppedRef.current) {
          dispatch({ type: "UTTERANCE_START" });
        }
      } catch (err) {
        silenceOther();
        if (
          playIdRef.current !== playId ||
          stoppedRef.current ||
          (err instanceof DOMException && err.name === "AbortError")
        ) {
          return;
        }
        console.error("[useTTS] play() failed", err);
        playChunkAtRef.current(idx + 1, playId);
      }
    },
    [armSecondary, clearAudioHandlers, clearHandoffWatch, prefetchAround],
  );

  useEffect(() => {
    handoffToNextRef.current = handoffToNext;
  }, [handoffToNext]);

  useEffect(() => {
    playPrimedChunkRef.current = (
      idx,
      playId,
      audio,
      pauseWhenPlaying,
      alreadyPlaying,
    ) => {
      void playPrimedChunk(idx, playId, audio, pauseWhenPlaying, alreadyPlaying);
    };
  }, [playPrimedChunk]);

  const playChunkAt = useCallback(
    async (idx: number, playId: number) => {
      if (playIdRef.current !== playId || stoppedRef.current) return;

      if (idx >= chunksRef.current.length) {
        finishPlayback();
        return;
      }

      currentChunkIdxRef.current = idx;
      const chunk = chunksRef.current[idx];

      dispatch({
        type: "CHUNK_START",
        currentIdx: chunk.startParagraphIdx,
        activeRange: {
          start: chunk.startParagraphIdx,
          end: chunk.endParagraphIdx,
        },
      });

      prefetchAround(idx, playId);

      let url: string;
      try {
        url = await ensureChunkUrl(chunk.text, voiceRef.current);
      } catch (err) {
        if (playIdRef.current !== playId || stoppedRef.current) return;
        console.error("[useTTS] chunk fetch failed", err);
        playChunkAtRef.current(idx + 1, playId);
        return;
      }

      if (playIdRef.current !== playId || stoppedRef.current) return;

      const audio = getPrimary();
      clearAudioHandlers(audio);
      // Pause secondary so only one stream
      const sec = secondaryRef.current;
      if (sec) {
        clearAudioHandlers(sec);
        sec.pause();
      }
      secondaryChunkRef.current = -1;
      handoffArmedRef.current = false;

      audio.src = url;
      audio.playbackRate = rateRef.current;
      try {
        audio.load();
      } catch {
        /* ignore */
      }

      try {
        await waitCanPlay(audio);
      } catch {
        /* try play anyway */
      }
      if (playIdRef.current !== playId || stoppedRef.current) return;

      playPrimedChunkRef.current(idx, playId, audio);
    },
    [
      clearAudioHandlers,
      ensureChunkUrl,
      finishPlayback,
      getPrimary,
      prefetchAround,
    ],
  );

  useEffect(() => {
    playChunkAtRef.current = (idx, playId) => {
      void playChunkAt(idx, playId);
    };
  }, [playChunkAt]);

  const ensureChunks = useCallback((key: string, paragraphs: string[]) => {
    const hasPrepared =
      preparedKeyRef.current === key && chunksRef.current.length > 0;
    if (!hasPrepared) {
      chunksRef.current = buildTTSChunks(paragraphs);
      preparedKeyRef.current = key;
    }
    return chunksRef.current;
  }, []);

  const prepare = useCallback(
    (key: string, paragraphs: string[]) => {
      if (!paragraphs.length) return;
      if (preparedKeyRef.current === key && chunksRef.current.length > 0) return;

      // Content/chapter changed: invalidate any in-flight playback so it cannot
      // continue speaking old audio against the new chunk list (or vice versa).
      // Do NOT set stoppedRef=false here — that is only for explicit play/resume.
      // (Previously prepare always set stoppedRef=false, which undid user Stop
      // when the prepare() identity changed and the effect re-ran.)
      if (preparedKeyRef.current !== null && preparedKeyRef.current !== key) {
        playIdRef.current += 1;
        stopAudio();
        currentChunkIdxRef.current = -1;
        dispatch({ type: "COMPLETE" });
      }

      ensureChunks(key, paragraphs);
      currentChunkIdxRef.current = -1;
      dispatch({
        type: "SET_TOTAL_CHUNKS",
        totalChunks: chunksRef.current.length,
      });

      // Warm pipeline while user still reading.
      // Fetch chunk 0 first (wins Edge concurrent slots) then tail — cold Play stays fast.
      const voice = voiceRef.current;
      const list = chunksRef.current;
      void (async () => {
        if (!list.length) return;
        try {
          await ensureChunkUrl(list[0].text, voice);
        } catch {
          /* ignore */
        }
        for (let i = 1; i < Math.min(WARM_ON_PREPARE, list.length); i++) {
          void ensureChunkUrl(list[i].text, voice).catch(() => {});
        }
      })();
    },
    [ensureChunkUrl, ensureChunks, stopAudio],
  );

  const beginPlayback = useCallback(
    (key: string, paragraphs: string[], startChunk: number) => {
      if (!paragraphs.length) return;

      stoppedRef.current = false;
      const newPlayId = ++playIdRef.current;

      stopAudio();
      ensureChunks(key, paragraphs);

      const safeStart =
        startChunk >= 0 && startChunk < chunksRef.current.length
          ? startChunk
          : 0;

      currentChunkIdxRef.current = safeStart;
      dispatch({ type: "START", totalChunks: chunksRef.current.length });
      void playChunkAt(safeStart, newPlayId);
    },
    [ensureChunks, playChunkAt, stopAudio],
  );

  const play = useCallback(
    (key: string, paragraphs: string[]) => {
      beginPlayback(key, paragraphs, 0);
    },
    [beginPlayback],
  );

  const playFromParagraph = useCallback(
    (key: string, paragraphs: string[], startParagraphIdx: number) => {
      ensureChunks(key, paragraphs);
      let startChunk = findChunkIndexForParagraph(
        chunksRef.current,
        startParagraphIdx,
      );
      if (startChunk < 0) startChunk = 0;
      beginPlayback(key, paragraphs, startChunk);
    },
    [beginPlayback, ensureChunks],
  );

  const pause = useCallback(() => {
    const audio = primaryRef.current;
    if (audio && !audio.paused) audio.pause();
    secondaryRef.current?.pause();
    dispatch({ type: "PAUSE" });
  }, []);

  const resume = useCallback(() => {
    const audio = primaryRef.current;
    if (audio) {
      audio.playbackRate = rateRef.current;
      void audio.play().catch(() => {});
    }
    dispatch({ type: "RESUME" });
  }, []);

  const stop = useCallback(() => {
    stoppedRef.current = true;
    playIdRef.current += 1;
    stopAudio();
    // Keep onCompleteRef — playId bump + cleared audio handlers prevent late fire.
    // Clearing it would break auto-next after user Stop → Play → finish chapter.
    chunksRef.current = [];
    currentChunkIdxRef.current = -1;
    preparedKeyRef.current = null;
    dispatch({ type: "STOP" });
  }, [stopAudio]);

  const skipForward = useCallback(() => {
    if (currentChunkIdxRef.current < 0) return;
    const nextIdx = currentChunkIdxRef.current + 1;
    if (nextIdx >= chunksRef.current.length) return;
    const newPlayId = ++playIdRef.current;
    stopAudio();
    dispatch({ type: "START", totalChunks: chunksRef.current.length });
    void playChunkAt(nextIdx, newPlayId);
  }, [playChunkAt, stopAudio]);

  const skipBackward = useCallback(() => {
    if (currentChunkIdxRef.current < 0) return;
    const targetIdx = Math.max(0, currentChunkIdxRef.current - 1);
    const newPlayId = ++playIdRef.current;
    stopAudio();
    dispatch({ type: "START", totalChunks: chunksRef.current.length });
    void playChunkAt(targetIdx, newPlayId);
  }, [playChunkAt, stopAudio]);

  const setRate = useCallback((newRate: number) => {
    if (rateRef.current === newRate) return;
    rateRef.current = newRate;
    setRateState(newRate);
    if (primaryRef.current) primaryRef.current.playbackRate = newRate;
    if (secondaryRef.current) secondaryRef.current.playbackRate = newRate;
  }, []);

  const setVoice = useCallback(
    (voiceName: string) => {
      if (!EDGE_VI_VOICES.some((v) => v.name === voiceName)) return;
      if (voiceRef.current === voiceName) return;

      voiceRef.current = voiceName;
      setSelectedVoiceName(voiceName);
      localStorage.setItem(VOICE_STORAGE_KEY, voiceName);

      stoppedRef.current = true;
      playIdRef.current += 1;
      stopAudio();
      currentChunkIdxRef.current = -1;
      dispatch({ type: "COMPLETE" });
    },
    [stopAudio],
  );

  const setOnChapterComplete = useCallback((cb: () => void) => {
    onCompleteRef.current = cb;
  }, []);

  useEffect(() => {
    return () => {
      stoppedRef.current = true;
      playIdRef.current += 1;
      stopAudio();
      revokeAllBlobs();
    };
  }, [revokeAllBlobs, stopAudio]);

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
