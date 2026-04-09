import type { Metadata, Viewport } from "next";
import "./globals.css";

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
    <html lang="vi">
      <body className="bg-[var(--color-bg)] text-[var(--color-text)] min-h-dvh">
        {children}
      </body>
    </html>
  );
}
