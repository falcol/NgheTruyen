"use client";

import { useState, useEffect } from "react";

interface ReadingProgress {
  chapterIdx: number;
  timestamp: number;
}

export function useProgress(slug: string) {
  const key = `progress-${slug}`;
  const [progress, setProgress] = useState<ReadingProgress | null>(null);

  useEffect(() => {
    const saved = localStorage.getItem(key);
    if (saved) {
      try {
        setProgress(JSON.parse(saved));
      } catch {
        // invalid JSON, ignore
      }
    }
  }, [key]);

  const save = (chapterIdx: number) => {
    const p: ReadingProgress = { chapterIdx, timestamp: Date.now() };
    localStorage.setItem(key, JSON.stringify(p));
    setProgress(p);
  };

  return { progress, save };
}
