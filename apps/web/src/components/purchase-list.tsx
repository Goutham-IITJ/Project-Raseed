import Link from "next/link";
import { useSession } from "./app-provider";
import { Icon } from "./icon";
import { Status } from "./ui";
import { dateTime, label, money } from "@/lib/format";
import type { Purchase } from "@/lib/types";
export function PurchaseList({ purchases, grouped = false, selected, onSelect, categories = new Map<string, string>() }: { purchases: Purchase[]; grouped?: boolean; selected?: string; onSelect?: (id: string) => void; categories?: Map<string, string> }) {
  const { profile } = useSession();
  return <div className="purchase-list">{purchases.map((purchase, index) => {
    const date = dateTime(purchase.purchased_at, profile.locale, profile.timezone);
    const previous = index > 0 ? dateTime(purchases[index - 1].purchased_at, profile.locale, profile.timezone) : null;
    const category = purchase.category_id ? categories.get(purchase.category_id) : undefined;
    return <div key={purchase.id}>{grouped && date !== previous && <h3 className="purchase-date">{date}</h3>}<Link href={"/purchases/" + purchase.id} className="purchase-row" aria-current={selected === purchase.id ? "true" : undefined} onClick={event => { if (onSelect && window.matchMedia("(min-width: 1100px)").matches && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey && event.button === 0) { event.preventDefault(); onSelect(purchase.id); } }}><span className="merchant-icon">{purchase.merchant_name_raw.slice(0, 1).toUpperCase()}</span><span className="purchase-description"><strong>{purchase.merchant_name_raw}</strong><small>{grouped ? category ?? `${purchase.line_items.length} items` : date}{purchase.payments[0] ? " · " + label(purchase.payments[0].method) : ""}</small></span><span className="purchase-status"><Status value={purchase.payment_status} /></span><strong className="amount">{money(purchase.grand_total, purchase.currency, profile.locale)}</strong><Icon name="chevron" size={17} /></Link></div>;
  })}</div>;
}
