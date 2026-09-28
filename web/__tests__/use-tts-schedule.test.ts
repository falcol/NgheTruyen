import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useTTS } from "@/hooks/useTTS";
import { buildTTSChunks } from "@/lib/tts-chunks";

class FakeAudio {
  static created: FakeAudio[] = [];
  src = "";
  preload = "auto";
  playbackRate = 1;
  paused = true;
  currentTime = 0;
  duration = 3;
  readyState = 0;
  preservesPitch = true;
  mozPreservesPitch = true;
  played = false;
  onended: null | (() => void) = null;
  onerror: null | (() => void) = null;
  onplaying: null | (() => void) = null;
  ontimeupdate: null | (() => void) = null;
  private listeners = new Map<string, Set<() => void>>();

  constructor() {
    FakeAudio.created.push(this);
  }

  load() {
    this.readyState = 4;
  }

  play() {
    this.played = true;
    this.paused = false;
    this.readyState = 4;
    this.onplaying?.();
    return Promise.resolve();
  }

  pause() {
    this.paused = true;
  }

  removeAttribute() {
    this.src = "";
  }

  addEventListener(type: string, fn: () => void) {
    const set = this.listeners.get(type) ?? new Set<() => void>();
    set.add(fn);
    this.listeners.set(type, set);
    if (type === "canplay" || type === "canplaythrough") fn();
  }

  removeEventListener(type: string, fn: () => void) {
    this.listeners.get(type)?.delete(fn);
  }
}

function paragraphsForChunks() {
  const sentence = "Người ấy đứng giữa sân và nhìn về phía dãy núi xa. ";
  return [sentence.repeat(20), sentence.repeat(30)];
}

describe("useTTS schedule", () => {
  const calls: string[] = [];
  const blocked = new Map<string, Promise<void>>();
  const release = new Map<string, () => void>();
  let root: Root | null = null;
  let host: HTMLDivElement | null = null;
  const slot: { api: ReturnType<typeof useTTS> | null } = { api: null };

  function block(text: string) {
    let done!: () => void;
    const gate = new Promise<void>((resolve) => {
      done = resolve;
    });
    blocked.set(text, gate);
    release.set(text, done);
  }

  async function settle(times = 6) {
    for (let i = 0; i < times; i++) {
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 0));
      });
    }
  }

  function Harness() {
    slot.api = useTTS();
    return null;
  }

  beforeEach(() => {
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    calls.length = 0;
    blocked.clear();
    release.clear();
    FakeAudio.created = [];
    localStorage.clear();
    let blobId = 0;
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: () => `blob:tts-${++blobId}`,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: () => {},
    });
    vi.stubGlobal("Audio", FakeAudio);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: { body?: string }) => {
        const text = JSON.parse(String(init?.body)).text as string;
        calls.push(text);
        const gate = blocked.get(text);
        if (gate) await gate;
        return new Response(new Uint8Array(128), { status: 200 });
      }),
    );
    host = document.createElement("div");
    document.body.appendChild(host);
    root = createRoot(host);
    act(() => {
      root?.render(createElement(Harness));
    });
  });

  afterEach(async () => {
    await act(async () => {
      root?.unmount();
    });
    host?.remove();
    root = null;
    host = null;
    slot.api = null;
    for (const done of release.values()) done();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("warms the opening chunk before play, starts on chunk 0, prefetches the next, and does not refetch", async () => {
    const paragraphs = paragraphsForChunks();
    const chunks = buildTTSChunks(paragraphs);
    expect(chunks.length).toBeGreaterThanOrEqual(2);
    const key = "schedule-chapter";
    for (const chunk of chunks.slice(1)) block(chunk.text);

    await act(async () => {
      slot.api?.prepare(key, paragraphs);
    });
    await settle();

    expect(calls).toContain(chunks[0].text);
    expect(calls.filter((text) => text === chunks[0].text)).toHaveLength(1);
    expect(FakeAudio.created.some((audio) => audio.played)).toBe(false);

    await act(async () => {
      slot.api?.play(key, paragraphs);
    });
    await settle();

    expect(FakeAudio.created.some((audio) => audio.played)).toBe(true);
    expect(calls).toContain(chunks[1].text);
    expect(release.get(chunks[1].text)).toBeTypeOf("function");

    for (const done of release.values()) done();
    release.clear();
    await settle(10);

    const playing = FakeAudio.created.find((audio) => audio.played && audio.onended);
    expect(playing?.onended).toBeTypeOf("function");
    const fetchesBeforeHandoff = calls.length;
    await act(async () => {
      playing?.onended?.();
    });
    await settle(8);

    expect(calls.filter((text) => text === chunks[0].text)).toHaveLength(1);
    expect(calls.filter((text) => text === chunks[1].text)).toHaveLength(1);
    expect(calls.length).toBeGreaterThanOrEqual(fetchesBeforeHandoff);

    await act(async () => {
      slot.api?.play(key, paragraphs);
    });
    await settle(8);

    expect(calls.filter((text) => text === chunks[0].text)).toHaveLength(1);
    expect(calls.filter((text) => text === chunks[1].text)).toHaveLength(1);
  });
});