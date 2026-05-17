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

const beVietnam = Be_Vietnam_Pro({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "700"],
  variable: "--font-be-vietnam",
});

const literata = Literata({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "700"],
  variable: "--font-literata",
});

const lora = Lora({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "700"],
  variable: "--font-lora",
});

const merriweather = Merriweather({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "700"],
  variable: "--font-merriweather",
});

const notoSerif = Noto_Serif({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "600", "700"],
  variable: "--font-noto-serif",
});

const sourceSerif = Source_Serif_4({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "600", "700"],
  variable: "--font-source-serif",
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
  maximumScale: 1,
  themeColor: "#0f0f0f",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi" className={fontVariables}>
      <body
        className={`${beVietnam.className} bg-[var(--color-bg)] text-[var(--color-text)] min-h-dvh`}
      >
        {children}
      </body>
    </html>
  );
}
