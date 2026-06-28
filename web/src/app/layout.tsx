import type { Metadata, Viewport } from "next";
import {
  Be_Vietnam_Pro,
  Literata,
  Lora,
  Merriweather,
  Noto_Serif,
  Source_Serif_4,
} from "next/font/google";
import "./globals.css";
import NavWrapper from "@/components/NavWrapper";

const beVietnam = Be_Vietnam_Pro({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "700"],
  variable: "--font-be-vietnam",
  display: "swap",
});

const literata = Literata({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "700"],
  variable: "--font-literata",
  display: "swap",
});

const lora = Lora({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "700"],
  variable: "--font-lora",
  display: "swap",
});

const merriweather = Merriweather({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "700"],
  variable: "--font-merriweather",
  display: "swap",
});

const notoSerif = Noto_Serif({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "600", "700"],
  variable: "--font-noto-serif",
  display: "swap",
});

const sourceSerif = Source_Serif_4({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "600", "700"],
  variable: "--font-source-serif",
  display: "swap",
});

const fontVariables = [
  beVietnam.variable,
  literata.variable,
  lora.variable,
  merriweather.variable,
  notoSerif.variable,
  sourceSerif.variable,
].join(" ");

export const metadata: Metadata = {
  title: "Nghe Truyện",
  description: "Đọc và nghe truyện cá nhân",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0f0f0f",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi" className={fontVariables} data-scroll-behavior="smooth">
      <body
        className={`${beVietnam.className} bg-[var(--color-bg)] text-[var(--color-text)] min-h-dvh overflow-x-hidden`}
      >
        <div className="ambient-blob ambient-blob-1" aria-hidden="true" />
        <div className="ambient-blob ambient-blob-2" aria-hidden="true" />
        <div className="ambient-blob ambient-blob-3" aria-hidden="true" />
        <NavWrapper>{children}</NavWrapper>
      </body>
    </html>
  );
}
