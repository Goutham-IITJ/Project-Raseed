import { dateTime, decimal, money } from "./format";
import type { Insight } from "./types";

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
function text(value: unknown): string | undefined { return typeof value === "string" ? value : undefined; }

// Format existing rule snapshots; do not derive a new signal or recompute a metric.
export function insightPresentation(insight: Insight, locale: string) {
  const source = insight.source_data;
  const lot = record(source.lot);
  const expiry = record(lot.expiry);
  if (insight.type === "INVENTORY_EXPIRY" && text(lot.name)) return {
    title: text(lot.name)!, metric: `${decimal(text(lot.quantity_remaining))} ${text(lot.unit) ?? ""}`,
    detail: `Recorded expiry ${dateTime(text(expiry.date) ?? null, locale)}`,
    note: `${text(expiry.provenance) === "INFERRED" ? "Estimated expiry" : "Recorded expiry"} · Check before use`,
    action: text(lot.item_id) ? `/inventory/${encodeURIComponent(text(lot.item_id)!)}` : undefined,
  };
  const metrics = record(source.metrics);
  const period = record(source.period);
  if (insight.type === "SPENDING_CHANGE" && text(metrics.percentage_change) && text(metrics.currency)) return {
    title: insight.title,
    metric: `${decimal(text(metrics.percentage_change))}%`,
    detail: `${money(text(metrics.current_total), text(metrics.currency)!, locale)} spent · ${money(text(metrics.absolute_change), text(metrics.currency)!, locale)} change`,
    note: `${dateTime(text(period.start_date) ?? null, locale)} – ${dateTime(text(period.end_date) ?? null, locale)} (end exclusive)`,
    action: undefined,
  };
  const current = record(source.current);
  if (insight.type === "UNUSUAL_PURCHASE" && text(current.largest_purchase) && text(current.currency)) return {
    title: insight.title,
    metric: money(text(current.largest_purchase), text(current.currency)!, locale),
    detail: insight.summary, note: "Largest purchase in the evaluated period",
    action: undefined,
  };
  return { title: insight.title, metric: undefined, detail: insight.summary, note: "From recorded purchases", action: undefined };
}
