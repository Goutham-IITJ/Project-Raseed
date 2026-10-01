"use client";
import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useSession } from "../app-provider";
import { PageHeader, ErrorState, Loading, Section } from "../ui";
import { PeriodSelect } from "../period-select";
import { CategoryRing, Change, PeriodBars, TrendChart } from "../charts";
import { CategoryComparison, MerchantRanking, PaymentBreakdown } from "../spending-breakdowns";
import { Icon } from "../icon";
import { useAnalytics } from "@/lib/use-analytics";
import { useResource } from "@/lib/use-resource";
import { dateTime, money } from "@/lib/format";
import type { Query } from "@/lib/types";

export function Analysis() {
  const { api, profile } = useSession();
  const [period, setPeriod] = useState("this_month");
  const [custom, setCustom] = useState<Query>({});
  const [currency, setCurrency] = useState(profile.currency);
  const [category, setCategory] = useState("");
  const [categoryName, setCategoryName] = useState("");
  const [merchant, setMerchant] = useState("");
  const [merchantName, setMerchantName] = useState("");
  const dates = period === "custom" && custom.start_date ? custom : { period: period === "custom" ? "this_month" : period };
  const query = { ...dates, currency, category_id: category, merchant_id: merchant };
  const finance = useAnalytics(query, true);
  const facets = useResource(async signal => {
    const [categories, merchants, summary] = await Promise.all([api.categories({ ...dates, limit: 100 }, signal), api.merchants({ ...dates, limit: 100 }, signal), api.summary(dates, signal)]);
    return { categories, merchants, summary };
  }, JSON.stringify(dates));
  const insights = useResource(signal => api.insights({ type: "SPENDING_CHANGE", limit: 5 }, signal), "spending-insights");
  function applyDates(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setCustom({ start_date: String(form.get("start_date")), end_date: String(form.get("end_date")) });
  }
  const awaitingDates = period === "custom" && !custom.start_date;
  const data = finance.data;
  const metrics = data?.summary.currencies.find(row => row.currency === currency);
  const change = data?.comparison.currencies.find(row => row.currency === currency);
  const categories = data?.categories.groups.filter(row => row.currency === currency) ?? [];
  const previous = data?.previousCategories?.groups.filter(row => row.currency === currency) ?? [];
  return <><PageHeader title="Analysis" actions={<PeriodSelect value={period} onChange={setPeriod} custom />} />
    <div className="analysis-filters"><label>Category<select aria-label="Analysis category" value={category} onChange={event => { setCategory(event.target.value); setCategoryName(event.target.selectedOptions[0].text); }}><option value="">All categories</option>{category && !facets.data?.categories.groups.some(row => row.category_id === category) && <option value={category}>{categoryName}</option>}{Array.from(new Map((facets.data?.categories.groups ?? []).filter(row => row.category_id).map(row => [row.category_id, row])).values()).map(row => <option key={row.category_id} value={row.category_id!}>{row.category_name}</option>)}</select></label><label>Merchant<select aria-label="Analysis merchant" value={merchant} onChange={event => { setMerchant(event.target.value); setMerchantName(event.target.selectedOptions[0].text); }}><option value="">All merchants</option>{merchant && !facets.data?.merchants.groups.some(row => row.merchant_id === merchant) && <option value={merchant}>{merchantName}</option>}{Array.from(new Map((facets.data?.merchants.groups ?? []).filter(row => row.merchant_id).map(row => [row.merchant_id, row])).values()).map(row => <option key={row.merchant_id} value={row.merchant_id!}>{row.merchant_name}</option>)}</select></label><label>Currency<select value={currency} onChange={event => setCurrency(event.target.value)}>{[...new Set([currency, profile.currency, ...(facets.data?.summary.currencies.map(row => row.currency) ?? [])])].map(value => <option key={value}>{value}</option>)}</select></label><span className="comparison-label"><Icon name="analysis" size={16} />Compared with previous period</span>{(category || merchant) && <button className="text-button" onClick={() => { setCategory(""); setMerchant(""); }}>Clear filters</button>}</div>
    {period === "custom" && <form className="custom-dates" onSubmit={applyDates}><label>From<input required name="start_date" type="date" defaultValue={custom.start_date ?? ""} /></label><label>Before (exclusive)<input required name="end_date" type="date" defaultValue={custom.end_date ?? ""} /></label><button className="button secondary">Apply dates</button></form>}
    {facets.error && <ErrorState message={"Filter choices could not load. " + facets.error} retry={facets.refresh} />}
    {awaitingDates ? <p className="help-text">Choose a start and end date, then apply them to view your analysis.</p> : finance.loading ? <Loading /> : finance.error ? <ErrorState message={finance.error} retry={finance.refresh} /> : data && <>
      <section className="analysis-hero"><div><span className="eyebrow">Total spending · {currency}</span><div className="hero-amount">{money(metrics?.total_spent, currency, profile.locale)}</div><div className="hero-comparison"><Change value={change?.percentage_change} /><span>vs previous period</span></div></div><div className="analysis-facts"><div><small>Purchases</small><strong>{metrics?.purchase_count ?? "Unavailable"}</strong></div><div><small>Average purchase</small><strong>{money(metrics?.average_purchase, currency, profile.locale)}</strong></div><div><small>Previous period</small><strong>{money(change?.comparison_total, currency, profile.locale)}</strong></div></div></section>
      <p className="data-note">{dateTime(data.summary.period.start_date, profile.locale)} – {dateTime(data.summary.period.end_date, profile.locale)} (end exclusive) · {data.summary.period.timezone} · Recorded purchases, all payment statuses</p>
      <div className="analysis-grid"><Section title="Spending over time" className="analysis-trend"><TrendChart key={JSON.stringify(query)} data={data.trend} currency={currency} /></Section>
        <Section title="Period comparison" className="analysis-period dark-module"><PeriodBars comparison={data.comparison} currency={currency} /></Section>
        <Section title="Where your money went" className="analysis-categories"><div className="category-analysis"><div><CategoryRing groups={categories.slice(0, 8)} total={metrics?.total_spent} currency={currency} /></div><div><h3>Category comparison</h3><CategoryComparison current={categories} previous={previous} currency={currency} currentHasMore={data.categories.has_more} previousHasMore={data.previousCategories?.has_more} /></div></div>{(data.categories.has_more || data.previousCategories?.has_more || categories.length > 8) && <p className="caption">Leading categories shown. Shares use the full total. Missing values in a partial list are unavailable.</p>}</Section>
        <Section title="Top merchants" className="analysis-merchants"><MerchantRanking groups={data.merchants.groups.filter(row => row.currency === currency).slice(0, 6)} />{data.merchants.has_more && <p className="caption">Leading merchants · shares of the full total</p>}</Section>
        <Section title="How you paid" className="analysis-payments"><PaymentBreakdown groups={data.payments.groups.filter(row => row.currency === currency)} /></Section>
      </div>
    </>}
    {insights.error ? <ErrorState message={insights.error} retry={insights.refresh} /> : insights.data && insights.data.length > 0 && <Section title="Spending insights" href="/insights" className="analysis-insights"><p className="caption">Latest evaluated observations · each has its own period and evidence</p>{insights.data.map(insight => <Link key={insight.id} href={"/insights/" + insight.id} className="analysis-insight"><Icon name="insights" /><div><strong>{insight.title}</strong><p>{insight.summary}</p><small>{dateTime(insight.evaluated_at, profile.locale)}</small></div><Icon name="arrow" /></Link>)}</Section>}
  </>;
}
