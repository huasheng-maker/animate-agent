import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Animate Agent — Knowledge Movie Studio",
  description: "Transform technical sources into interactive knowledge movies.",
  icons: { icon: "/icon.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
