"use client";
import { useState } from "react";
import Link from "next/link";
import { useSession } from "../app-provider";
import { Icon } from "../icon";
import { Badge, EmptyState, ErrorState, Evidence, Loading, PageHeader, Pager, Status } from "../ui";
import { useResource } from "@/lib/use-resource";
import { dateTime, decimal, label } from "@/lib/format";
export function Insights() {
  const { api, profile } = useSession();
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const insights = useResource(signal => api.insights({ type, status, offset, limit: 20 }, signal), type + status + offset);
  return <><PageHeader eyebrow="A LITTLE PERSPECTIVE" title="Good things to know." description="Thoughtful observations from your recorded spending and the things you keep at home." /><div className="toolbar"><div className="segmented" aria-label="Insight categories">{[["", "All insights"], ["SPENDING_CHANGE", "Spending"], ["UNUSUAL_PURCHASE", "Purchases"], ["INVENTORY_EXPIRY", "Inventory"]].map(([value, name]) => <button key={value} aria-pressed={type === value} onClick={() => { setType(value); setOffset(0); }}>{name}</button>)}</div><label className="select-label"><span className="sr-only">Insight status</span><select value={status} onChange={event => { setStatus(event.target.value); setOffset(0); }}><option value="">Current insights</option>{["ACTIVE", "READ", "DISMISSED", "RESOLVED", "EXPIRED"].map(value => <option key={value} value={value}>{label(value)}</option>)}</select></label></div><section className="section">{insights.loading ? <Loading /> : insights.error ? <ErrorState message={insights.error} retry={insights.refresh} /> : insights.data?.length ? <><div className="insight-feed">{insights.data.map(insight => <Link href={"/insights/" + insight.id} key={insight.id} className="insight-article"><span className={"soft-icon " + (insight.type === "INVENTORY_EXPIRY" ? "amber" : "")}><Icon name={insight.type === "INVENTORY_EXPIRY" ? "clock" : "insights"} size={24} /></span><div><div className="insight-meta"><span>{label(insight.type)}</span><Status value={insight.status} /></div><h2>{insight.title}</h2><p>{insight.summary}</p><small>Evaluated {dateTime(insight.evaluated_at, profile.locale, profile.timezone)} · View the evidence</small></div><Icon name="arrow" size={18} /></Link>)}</div><Pager offset={offset} count={insights.data.length} onChange={setOffset} /></> : <><EmptyState icon="insights" title="Nothing to flag just yet">Insights appear when your recorded purchases or inventory support a useful observation. There’s no need to fill the silence.</EmptyState><Pager offset={offset} count={0} onChange={setOffset} /></>}</section></>;
}
export function InsightDetail({ id }: { id: string }) {
  const { api, profile } = useSession();
  const insight = useResource(signal => api.insight(id, signal), id);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  async function change(status: "READ" | "DISMISSED") {
    if (!insight.data || busy) return;
    setBusy(true); setError(undefined);
    try { await api.updateInsight(id, status, insight.data.version); insight.refresh(); }
    catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  if (insight.loading) return <Loading />;
  if (insight.error || !insight.data) return <ErrorState message={insight.error} retry={insight.refresh} />;
  const item = insight.data;
  return <><Link href="/insights" className="back-link"><Icon name="back" size={17} />All insights</Link><PageHeader eyebrow={label(item.type)} title={item.title} actions={<Status value={item.status} />} /><article className="insight-detail section"><span className="soft-icon"><Icon name="insights" size={26} /></span><p className="insight-summary">{item.summary}</p><div className="evidence-notice"><Icon name="shield" size={18} /><p>Based on recorded evidence at the time of evaluation. Current spending or inventory may have changed.</p></div><dl className="facts"><div><dt>Evaluated</dt><dd>{dateTime(item.evaluated_at, profile.locale, profile.timezone, true)}</dd></div><div><dt>Expires</dt><dd>{dateTime(item.expires_at, profile.locale, profile.timezone, true)}</dd></div><div><dt>Provenance</dt><dd><Badge>{label(item.provenance)}</Badge></dd></div><div><dt>Evidence confidence</dt><dd>{item.confidence == null ? "Not assigned to this calculation" : decimal(item.confidence) + " / 1"}</dd></div></dl><details className="evidence-details" open><summary>Evidence behind this insight</summary><Evidence value={item.source_data} /></details><details className="evidence-details"><summary>How this was identified</summary><Evidence value={item.calculation} /></details>{["ACTIVE", "READ"].includes(item.status) && <div className="actions"><button className="button secondary" disabled={busy || item.status === "READ"} onClick={() => void change("READ")}><Icon name="check" size={17} />Mark as read</button><button className="text-button" disabled={busy} onClick={() => void change("DISMISSED")}>Dismiss insight</button></div>}{error && <ErrorState message={error} retry={insight.refresh} />}</article></>;
}
