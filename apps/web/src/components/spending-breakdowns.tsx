import { useSession } from "./app-provider";
import { percent } from "./charts";
import { money, label } from "@/lib/format";
import type { CategoryGroup, Merchants, PaymentDistribution } from "@/lib/types";

export function MerchantRanking({ groups }: { groups: Merchants["groups"] }) {
  const { profile } = useSession();
  if (!groups.length) return <p className="muted">No merchants in this period.</p>;
  return <ol className="merchant-ranking">{groups.map((row, i) => <li key={row.merchant_id ?? "none"}><span className="rank-number">{String(i + 1).padStart(2, "0")}</span><div><div className="rank-label"><strong>{row.merchant_name ?? "Unassigned merchant"}</strong><span>{money(row.total_spent, row.currency, profile.locale)}</span></div><div className="rank-track"><span style={{ width: `${Number(row.share_of_total_percent ?? 0)}%` }} /></div><small>{row.purchase_count} purchases <span>{percent(row.share_of_total_percent)}</span></small></div></li>)}</ol>;
}
export function PaymentBreakdown({ groups }: { groups: PaymentDistribution["groups"] }) {
  const { profile } = useSession();
  return <>{groups.length ? <div className="payment-breakdown">{groups.map((row, i) => <div key={row.method}><div className="rank-label"><strong>{label(row.method)}</strong><span>{money(row.total_amount, row.currency, profile.locale)}</span></div><div className={"payment-track shade-" + i % 3}><span style={{ width: `${Number(row.share_of_total_percent ?? 0)}%` }} /></div><small>{row.payment_count} recorded payments · {percent(row.share_of_total_percent)}</small></div>)}</div> : <p className="muted">No payment details recorded.</p>}<p className="caption">Recorded payments only. Purchases may have missing payment details.</p></>;
}
export function CategoryComparison({ current, previous, currency, currentHasMore = false, previousHasMore = false }: { current: CategoryGroup[]; previous: CategoryGroup[]; currency: string; currentHasMore?: boolean; previousHasMore?: boolean }) {
  const { profile } = useSession();
  const ids = [...new Set([...current, ...previous].map(row => row.category_id))];
  const rows = ids.map(id => ({ current: current.find(row => row.category_id === id), previous: previous.find(row => row.category_id === id) }));
  const maximum = Math.max(...[...current, ...previous].map(row => Number(row.total_amount ?? 0)), 1);
  return <><div className="chart-key"><span><i />Selected</span><span><i />Previous</span></div><div className="category-comparison">{rows.slice(0, 8).map(row => {
    const selected = row.current ? row.current.total_amount : currentHasMore ? null : "0";
    const prior = row.previous ? row.previous.total_amount : previousHasMore ? null : "0";
    return <div key={row.current?.category_id ?? row.previous?.category_id ?? "none"}><strong>{row.current?.category_name ?? row.previous?.category_name ?? "Unassigned"}</strong>{[["Selected", selected], ["Previous", prior]].map(([name, amount]) => <div key={name} className={"paired-bar " + (name === "Previous" ? "previous" : "")}><div className="paired-track" aria-hidden="true"><span style={{ width: `${Number(amount ?? 0) / maximum * 100}%` }} /></div><small><span className="sr-only">{name}: </span>{amount == null ? "Unavailable" : money(amount, currency, profile.locale)}</small></div>)}</div>;
  })}</div>{!rows.length && <p className="muted">No categories in either period.</p>}{rows.length > 8 && <p className="caption">Showing eight categories.</p>}</>;
}
