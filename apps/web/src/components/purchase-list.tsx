import Link from "next/link";
import { useSession } from "./app-provider";
import { Icon } from "./icon";
import { Status } from "./ui";
import { dateTime, money } from "@/lib/format";
import type { Purchase } from "@/lib/types";
export function PurchaseList({ purchases }: { purchases: Purchase[] }) {
  const { profile } = useSession();
  return <div className="purchase-list">{purchases.map(purchase => <Link href={"/purchases/" + purchase.id} className="purchase-row" key={purchase.id}><span className="merchant-icon">{purchase.merchant_name_raw.slice(0, 1).toUpperCase()}</span><span className="purchase-description"><strong>{purchase.merchant_name_raw}</strong><small>{dateTime(purchase.purchased_at, profile.locale, profile.timezone)} · {purchase.line_items.length} recorded {purchase.line_items.length === 1 ? "item" : "items"}</small></span><span className="purchase-status"><Status value={purchase.payment_status} /></span><strong className="amount">{money(purchase.grand_total, purchase.currency, profile.locale)}</strong><Icon name="chevron" size={17} /></Link>)}</div>;
}
