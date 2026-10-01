"use client";
import { useId, useState } from "react";
import { useSession } from "./app-provider";
import { dateTime, money } from "@/lib/format";
import type { CategoryGroup, Comparison, Trend } from "@/lib/types";

// Numeric conversions below are for SVG geometry and rounded presentation only.
// All financial totals, ratios, buckets and changes are supplied by AnalyticsService.
export const chartColors = ["#13825e", "#a7c95a", "#648a81", "#bdc6c1", "#a99d84", "#455c56"];
export function percent(value: string | null | undefined) {
  return value == null ? "—" : new Intl.NumberFormat("en", { maximumFractionDigits: 1 }).format(Number(value)) + "%";
}
export function Change({ value }: { value: string | null | undefined }) {
  const unchanged = value != null && Number(value) === 0;
  return <span className={"change " + (value == null || unchanged ? "neutral" : value.startsWith("-") ? "decrease" : "increase")}>{value === undefined ? "Comparison unavailable" : value === null ? "No prior spending" : unchanged ? "No change" : (value.startsWith("-") ? "↘ " : "↗ ") + percent(value.replace(/^-/, ""))}</span>;
}
export function TrendChart({ data, currency }: { data: Trend; currency: string }) {
  const { profile } = useSession();
  const gradient = useId();
  const [active, setActive] = useState<number | null>(null);
  const rows = data.points.filter(point => point.currency === currency);
  const maximum = Math.max(...rows.map(row => Number(row.total_spent)), 0);
  const highest = rows.find(row => Number(row.total_spent) === maximum);
  const width = 800, height = 200;
  const x = (index: number) => 10 + index * (width - 20) / Math.max(1, rows.length - 1);
  const y = (amount: string) => height - (Number(amount) / (maximum || 1)) * (height - 16);
  const line = rows.map((row, i) => `${i ? "L" : "M"}${x(i)},${y(row.total_spent)}`).join(" ");
  const selected = active == null ? undefined : rows[active];
  const instructions = useId();
  if (!rows.length) return <div className="chart-empty">No spending recorded for this period.</div>;
  return <div className="trend-chart">
    <div className="chart-scale"><span>{money(highest?.total_spent ?? "0", currency, profile.locale)}</span><span>{data.interval === "day" ? "Daily spending" : "Monthly spending"}</span></div>
    <p id={instructions} className="sr-only">Use the arrow keys to explore dates, or open the chart data table below.</p>
    <svg viewBox={`0 0 ${width} ${height + 10}`} className="trend-svg" role="group" aria-label="Spending over time" aria-describedby={instructions}>
      <defs><linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#13825e" stopOpacity=".22" /><stop offset="100%" stopColor="#13825e" stopOpacity=".015" /></linearGradient></defs>
      {[0, 1, 2, 3].map(i => <line key={i} x1="0" x2={width} y1={16 + i * (height - 16) / 3} y2={16 + i * (height - 16) / 3} className="chart-gridline" />)}
      <path d={`${line} L${x(rows.length - 1)},${height} L${x(0)},${height} Z`} fill={`url(#${gradient})`} />
      <path d={line} fill="none" stroke="#13825e" strokeWidth="3" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      {rows.map((row, i) => {
        const left = i === 0 ? 0 : (x(i - 1) + x(i)) / 2;
        const right = i === rows.length - 1 ? width : (x(i) + x(i + 1)) / 2;
        return <g key={row.date}><circle cx={x(i)} cy={y(row.total_spent)} r={active === i ? 5 : rows.length === 1 ? 4 : 0} fill="#13825e" stroke="white" strokeWidth="2" /><rect x={left} y="0" width={right - left} height={height + 10} fill="transparent" tabIndex={i === (active ?? 0) ? 0 : -1} role="button" aria-label={`${dateTime(row.date, profile.locale)}: ${money(row.total_spent, currency, profile.locale)}, ${row.purchase_count} purchases`} onMouseEnter={() => setActive(i)} onFocus={() => setActive(i)} onClick={() => setActive(i)} onKeyDown={event => {
          const next = event.key === "ArrowRight" ? Math.min(rows.length - 1, i + 1) : event.key === "ArrowLeft" ? Math.max(0, i - 1) : event.key === "Home" ? 0 : event.key === "End" ? rows.length - 1 : null;
          if (next != null) { event.preventDefault(); event.currentTarget.ownerSVGElement?.querySelectorAll<SVGRectElement>("rect")[next]?.focus(); }
          else if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setActive(i); }
        }}><title>{dateTime(row.date, profile.locale)} · {money(row.total_spent, currency, profile.locale)}</title></rect></g>;
      })}
    </svg>
    <div className="chart-dates">{rows.filter((_, i) => i === 0 || i === rows.length - 1 || (rows.length > 4 && i === Math.floor(rows.length / 2))).map(row => <span key={row.date}>{dateTime(row.date, profile.locale)}</span>)}</div>
    <div className="chart-readout" aria-live="polite">{selected ? <><span>{dateTime(selected.date, profile.locale)}</span><strong>{money(selected.total_spent, currency, profile.locale)}</strong><span>{selected.purchase_count} purchases</span></> : <><span className="legend-dot" />Recorded purchase totals <span className="chart-hint">Select a point for details</span></>}</div>
    <details className="chart-data"><summary>View chart data</summary><div className="table-scroll"><table><caption>Spending over time · {currency}</caption><thead><tr><th>Date</th><th>Spending</th><th>Purchases</th></tr></thead><tbody>{rows.map(row => <tr key={row.date}><td>{dateTime(row.date, profile.locale)}</td><td>{money(row.total_spent, currency, profile.locale)}</td><td>{row.purchase_count}</td></tr>)}</tbody></table></div></details>
  </div>;
}
export function CategoryRing({ groups, total, currency }: { groups: CategoryGroup[]; total: string | undefined; currency: string }) {
  const { profile } = useSession();
  const shares = groups.map(row => Math.min(100, Math.max(0, Number(row.share_of_known_total_percent ?? 0))));
  const arcs = groups.map((row, index) => {
    const share = shares[index];
    const offset = shares.slice(0, index).reduce((sum, value) => sum + value, 0);
    return <circle key={row.category_id ?? "none"} cx="100" cy="100" r="78" fill="none" stroke={chartColors[index % chartColors.length]} strokeWidth="22" pathLength="100" strokeDasharray={`${share} ${100 - share}`} strokeDashoffset={-offset} transform="rotate(-90 100 100)"><title>{row.category_name ?? "Unassigned"}: {money(row.total_amount, currency, profile.locale)} · {row.share_of_known_total_percent == null ? "Share unavailable" : row.share_of_known_total_percent + "%"}</title></circle>;
  });
  return <><div className="ring-wrap"><svg viewBox="0 0 200 200" role="img" aria-label="Spending by category"><circle cx="100" cy="100" r="78" fill="none" stroke="currentColor" opacity=".12" strokeWidth="22" />{arcs}</svg><div className="ring-center"><small>Total spending</small><strong>{money(total, currency, profile.locale)}</strong></div></div><div className="ring-legend">{groups.map((row, i) => <div key={row.category_id ?? "none"}><span className="legend-dot" style={{ background: chartColors[i % chartColors.length] }} /><span>{row.category_name ?? "Unassigned"}</span><strong>{percent(row.share_of_known_total_percent)}</strong></div>)}</div></>;
}
export function PeriodBars({ comparison, currency }: { comparison: Comparison; currency: string }) {
  const { profile } = useSession();
  const row = comparison.currencies.find(item => item.currency === currency);
  if (!row) return <p className="muted">No comparison available.</p>;
  const max = Math.max(Number(row.current_total), Number(row.comparison_total), 1);
  return <div className="period-bars"><div className="comparison-columns">{[["Previous", row.comparison_total], ["Selected", row.current_total]].map(([name, value]) => <div key={name}><strong>{money(value, currency, profile.locale)}</strong><div className="column-track"><span style={{ height: `${Number(value) / max * 100}%` }} /></div><small>{name}</small></div>)}</div><div className="comparison-note"><Change value={row.percentage_change} /><span>{money(row.absolute_change, currency, profile.locale)} change</span></div><small className="period-note">Previous: {dateTime(comparison.comparison_period.start_date, profile.locale)} – {dateTime(comparison.comparison_period.end_date, profile.locale)} (end exclusive)</small></div>;
}
