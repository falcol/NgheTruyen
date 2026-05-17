"use client";

import { createContext, useContext } from "react";
import { useReaderSettings } from "@/hooks/useReaderSettings";

type ReaderSettingsValue = ReturnType<typeof useReaderSettings>;

const ReaderSettingsContext = createContext<ReaderSettingsValue | null>(null);

export function ReaderSettingsProvider({ children }: { children: React.ReactNode }) {
  const value = useReaderSettings();
  return (
    <ReaderSettingsContext.Provider value={value}>
      {children}
    </ReaderSettingsContext.Provider>
  );
}

export function useReaderSettingsContext(): ReaderSettingsValue {
  const ctx = useContext(ReaderSettingsContext);
  if (!ctx) {
    throw new Error("useReaderSettingsContext must be used within ReaderSettingsProvider");
  }
  return ctx;
}
