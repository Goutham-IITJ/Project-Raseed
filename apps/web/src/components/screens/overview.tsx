"use client";
import { useState } from "react";
import Link from "next/link";
import { useSession } from "../app-provider";
import { Icon } from "../icon";
import { EmptyState, ErrorState, Loading, PageHeader, Section, Status } from "../ui";
import { PurchaseList } from "../purchase-list";
import { CategoryRing, Change, TrendChart } from "../charts";
import { AddReceipt } from "../shell";
import { PeriodSelect } from "../period-select";
import { MerchantRanking } from "../spending-breakdowns";
import { useResource } from "@/lib/use-resource";
import { useAnalytics } from "@/lib/use-analytics";
import { dateTime, decimal, money } from "@/lib/format";

export function Overview() {
  const { api, profile } = useSession();
  const [period, setPeriod] = useState("this_month");
  const [currency, setCurrency] = useState(profile.currency);
  const finance = useAnalytics({ period });
  const recent = useResource(signal => api.purchases({ limit: 5 }, signal), "recent");
  const lots = useResource(signal => api.lots({ limit: 100 }, signal), "attention");
  const metrics = finance.data?.summary.currencies.find(row => row.currency === currency) ?? finance.data?.summary.currencies[0];
  const change = finance.data?.comparison.currencies.find(row => row.currency === metrics?.currency);
  const groups = finance.data?.categories.groups.filter(row => row.currency === metrics?.currency) ?? [];
  const attention = lots.data?.filter(lot => ["DUE", "PAST_DUE"].includes(lot.expiry.status) && decimal(lot.quantity_remaining) !== "0") ?? [];
  return <><PageHeader eyebrow="Overview" title={"Hello, " + (profile.display_name?.split(" ")[0] ?? "there") + "."} actions={<PeriodSelect label="Overview period" value={period} onChange={setPeriod} />} />
    {finance.loading ? <Loading /> : finance.error ? <ErrorState message={finance.error} retry={finance.refresh} /> : finance.data && metrics ? <>
      <div className="overview-finance"><section className="spending-workspace"><div className="metric-heading"><span>Total spending</span><label className="currency-select"><span className="sr-only">Spending currency</span><select value={metrics.currency} onChange={event => setCurrency(event.target.value)}>{finance.data.summary.currencies.map(row => <option key={row.currency}>{row.currency}</option>)}</select></label></div><div className="hero-amount">{money(metrics.total_spent, metrics.currency, profile.locale)}</div><div className="hero-comparison"><Change value={change?.percentage_change} /><span>vs previous period</span><Link href="/analysis" className="text-link">Explore analysis<Icon name="arrow" size={16} /></Link></div>
        <div className="metric-strip"><div><small>Purchases</small><strong>{metrics.purchase_count}</strong></div><div><small>Average purchase</small><strong>{money(metrics.average_purchase, metrics.currency, profile.locale)}</strong></div><div><small>Previous period</small><strong>{money(change?.comparison_total, metrics.currency, profile.locale)}</strong></div></div>
        <TrendChart key={period + metrics.currency} data={finance.data.trend} currency={metrics.currency} />
      </section><section className="category-focus"><div className="section-heading"><h2>Where it went</h2><Icon name="analysis" /></div><CategoryRing groups={groups.slice(0, 6)} total={metrics.total_spent} currency={metrics.currency} />{(groups.length > 6 || finance.data.categories.has_more) && <p className="caption">Leading categories · shares of the full total</p>}<Link href="/analysis" className="category-action">Category breakdown<Icon name="arrow" size={17} /></Link></section></div>
      <p className="data-note">{dateTime(finance.data.summary.period.start_date, profile.locale)} – {dateTime(finance.data.summary.period.end_date, profile.locale)} (end exclusive) · {finance.data.summary.period.timezone} · Currencies kept separate</p>
    </> : <section className="section"><EmptyState title="No spending recorded" action={<AddReceipt />}>No purchases in this period. Choose another period or add a receipt.</EmptyState></section>}
    <div className="overview-lower"><Section title="Recent purchases" href="/purchases" className="recent-module">{recent.loading ? <Loading /> : recent.error ? <ErrorState message={recent.error} retry={recent.refresh} /> : recent.data?.length ? <PurchaseList purchases={recent.data} /> : <EmptyState title="No purchases yet">Add your first receipt.</EmptyState>}</Section>
      <div className="overview-context"><Section title="Needs attention" href="/inventory" className="attention-module">{lots.loading ? <Loading compact /> : lots.error ? <ErrorState message={lots.error} retry={lots.refresh} /> : attention.length ? <>{attention.slice(0, 3).map(lot => <Link href={"/inventory/" + lot.item_id} className="attention-row" key={lot.id}><span className="soft-icon amber"><Icon name="clock" /></span><div><strong>{lot.name}</strong><small>{decimal(lot.quantity_remaining)} {lot.unit} · {dateTime(lot.expiry.date, profile.locale)}</small></div><Status value={lot.expiry.status} /></Link>)}<small className="caption">Recorded expiry · latest 100 lots</small></> : <div className="quiet-state"><Icon name="check" /><span>No recorded expiry alerts</span></div>}</Section>
      {finance.data && metrics && <Section title="Top merchants" href="/analysis" className="merchant-module"><MerchantRanking groups={finance.data.merchants.groups.filter(row => row.currency === metrics.currency).slice(0, 3)} /></Section>}</div>
    </div>
  </>;
}
