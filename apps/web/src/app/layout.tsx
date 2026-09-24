import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Raseed · Your account",
  description: "Your Raseed account",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
