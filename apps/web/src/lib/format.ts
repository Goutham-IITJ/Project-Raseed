export function label(value: string) { return value.toLowerCase().replaceAll("_", " ").replace(/^\w/, char => char.toUpperCase()); }
export function decimal(value: string | null | undefined) {
  if (value == null) return "Not recorded";
  return value.includes(".") ? value.replace(/0+$/, "").replace(/\.$/, "") : value;
}
// Presentation only: preserve decimal precision without converting money to Number.
export function money(value: string | null | undefined, currency: string, locale = "en-IN"): string {
  if (value == null) return "Not recorded";
  if (!/^-?\d+(\.\d+)?$/.test(value)) return "Unavailable";
  const [whole, fraction = ""] = value.replace(/^-/, "").split(".");
  try {
    const format = new Intl.NumberFormat(locale, { style: "currency", currency, maximumFractionDigits: 6, minimumFractionDigits: Math.max(fraction.replace(/0+$/, "").length, new Intl.NumberFormat(locale, { style: "currency", currency }).resolvedOptions().minimumFractionDigits ?? 0) });
    const minimum = format.resolvedOptions().minimumFractionDigits ?? 2;
    const digits = fraction.replace(/0+$/, "").padEnd(minimum, "0");
    const integer = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(BigInt(whole));
    let written = false;
    return format.formatToParts(value.startsWith("-") ? -1n : 1n).map(part => {
      if (part.type === "integer") { if (written) return ""; written = true; return integer; }
      if (part.type === "group") return "";
      if (part.type === "fraction") return digits;
      if (part.type === "decimal") return digits ? part.value : "";
      return part.value;
    }).join("");
  } catch { return currency + " " + decimal(value); }
}
export function dateTime(value: string | null, locale = "en-IN", timezone = "Asia/Kolkata", withTime = false) {
  if (!value) return "Not recorded";
  const date = new Date(value.length === 10 ? value + "T12:00:00Z" : value);
  if (Number.isNaN(date.getTime())) return "Unavailable";
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", ...(withTime ? { timeStyle: "short" as const } : {}), timeZone: value.length === 10 ? "UTC" : timezone }).format(date);
}
