import type { CSSProperties } from "react";
const paths = {
  overview: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  receipt: "M6 3h12v19l-3-2-3 2-3-2-3 2V3Z M9 7h6 M9 11h6 M9 15h3",
  inventory: "m3 7 9-4 9 4v12l-9 3-9-3V7Z m0 0 9 4 9-4 M12 11v11 M7 5l10 4",
  insights: "M12 3v2 M3 12h2 M19 12h2 M5 5l2 2 M17 7l2-2 M9 18h6 M9 21h6 M8 15a6 6 0 1 1 8 0l-1 3H9l-1-3",
  assistant: "M21 11a9 9 0 0 1-9 9H4l-2 2V11a9 9 0 0 1 19 0Z M8 11h.01 M12 11h.01 M16 11h.01",
  wallet: "M20 8V5H5a2 2 0 0 0 0 4h16v12H5a2 2 0 0 1-2-2V7 M21 12h-6v5h6 M17 14.5h.01",
  settings: "m9 3-1 3-3 1-2 3 2 2-1 3 3 3 3-1 2 2 3-1 1-3 3-1 1-3-2-2 1-3-3-3-3 1-2-2Z M15 11a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
  plus: "M12 5v14 M5 12h14", arrow: "M5 12h14 M13 6l6 6-6 6", back: "M19 12H5 M11 6l-6 6 6 6",
  chevron: "m9 5 7 7-7 7", down: "m6 9 6 6 6-6", close: "m6 6 12 12 M6 18 18 6",
  search: "M10 18a8 8 0 1 0 0-16 8 8 0 0 0 0 16 M16 16l6 6",
  upload: "M12 16V3 M6 9l6-6 6 6 M4 16v5h16v-5",
  check: "m5 12 4 4L19 6", warning: "m12 3 10 18H2L12 3Z M12 9v5 M12 17h.01",
  refresh: "M20 7a9 9 0 1 0 1 10 M20 2v6h-6",
  menu: "M3 6h18 M3 12h18 M3 18h18", logout: "M9 3H3v18h6 M9 12h12 M16 7l5 5-5 5",
  calendar: "M4 5h16v16H4z M8 2v6 M16 2v6 M4 10h16", clock: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M12 6v6l4 2",
  external: "M14 3h7v7 M10 14 21 3 M10 3H3v18h18v-7",
  shield: "m12 2 9 4v7c0 5-9 9-9 9s-9-4-9-9V6l9-4Z m-4 10 3 3 5-6",
  spark: "m12 2 2.5 7.5L22 12l-7.5 2.5L12 22l-2.5-7.5L2 12l7.5-2.5L12 2Z",
  leaf: "M20 3C8 2 2 8 5 16c8 4 15-2 15-13Z M4 21 16 8",
  send: "m3 3 19 9-19 9 4-9-4-9Z M7 12h15",
  file: "M14 2H4v20h16V8l-6-6Z M14 2v6h6 M8 13h8 M8 17h5",
};
export type IconName = keyof typeof paths;
export function Icon({ name, size = 20, style, className = "" }: { name: IconName; size?: number; style?: CSSProperties; className?: string }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={style} className={className}><path d={paths[name]} /></svg>;
}
