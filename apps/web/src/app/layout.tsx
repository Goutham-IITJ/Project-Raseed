import type { Metadata } from "next";
import { AppProvider } from "@/components/app-provider";
import { Shell } from "@/components/shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Raseed · Your purchase memory",
  description: "A little clarity for the things you buy. Your receipts, spending, inventory and answers, remembered together.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body><AppProvider><Shell>{children}</Shell></AppProvider></body>
    </html>
  );
}
