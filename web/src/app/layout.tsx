import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "./globals.css";
import NavWrapper from "@/components/NavWrapper";

// Self-hosted Google Fonts (latin + vietnamese, 400/500/700).
// next/font/google downloads at build time and breaks Turbopack builds when
// fonts.googleapis.com is unreachable — local files build deterministically.
const beVietnam = localFont({
  src: [
    { path: "../fonts/BeVietnamPro-400-latin.woff2", weight: "400", style: "normal" },
    { path: "../fonts/BeVietnamPro-400-vietnamese.woff2", weight: "400", style: "normal" },
    { path: "../fonts/BeVietnamPro-500-latin.woff2", weight: "500", style: "normal" },
    { path: "../fonts/BeVietnamPro-500-vietnamese.woff2", weight: "500", style: "normal" },
    { path: "../fonts/BeVietnamPro-700-latin.woff2", weight: "700", style: "normal" },
    { path: "../fonts/BeVietnamPro-700-vietnamese.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-be-vietnam",
  display: "swap",
});

const literata = localFont({
  src: [
    { path: "../fonts/Literata-400-latin.woff2", weight: "400", style: "normal" },
    { path: "../fonts/Literata-400-vietnamese.woff2", weight: "400", style: "normal" },
    { path: "../fonts/Literata-500-latin.woff2", weight: "500", style: "normal" },
    { path: "../fonts/Literata-500-vietnamese.woff2", weight: "500", style: "normal" },
    { path: "../fonts/Literata-700-latin.woff2", weight: "700", style: "normal" },
    { path: "../fonts/Literata-700-vietnamese.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-literata",
  display: "swap",
});

const lora = localFont({
  src: [
    { path: "../fonts/Lora-400-latin.woff2", weight: "400", style: "normal" },
    { path: "../fonts/Lora-400-vietnamese.woff2", weight: "400", style: "normal" },
    { path: "../fonts/Lora-500-latin.woff2", weight: "500", style: "normal" },
    { path: "../fonts/Lora-500-vietnamese.woff2", weight: "500", style: "normal" },
    { path: "../fonts/Lora-700-latin.woff2", weight: "700", style: "normal" },
    { path: "../fonts/Lora-700-vietnamese.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-lora",
  display: "swap",
});

const fontVariables = [
  beVietnam.variable,
  literata.variable,
  lora.variable,
].join(" ");

export const metadata: Metadata = {
  title: "Nghe Truyện",
  description: "Đọc và nghe truyện cá nhân",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#06070f",
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
        <NavWrapper>{children}</NavWrapper>
      </body>
    </html>
  );
}
