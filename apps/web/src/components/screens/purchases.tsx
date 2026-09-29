"use client";
import { useState, type FormEvent } from "react";
import { useSession } from "../app-provider";
import { Icon } from "../icon";
import { EmptyState, ErrorState, Loading, Modal, PageHeader, Pager, Status } from "../ui";
import { AddReceipt } from "../shell";
import { PurchaseList } from "../purchase-list";
import { ReceiptProgress } from "../upload";
import { useResource } from "@/lib/use-resource";
import type { Query, Receipt } from "@/lib/types";
export function Purchases() {
  const { api } = useSession();
  const [filters, setFilters] = useState<Query>({});
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Receipt | null>(null);
  const query = { ...filters, limit: 20, offset };
  const list = useResource(signal => api.purchases(query, signal), JSON.stringify(query));
  const receipts = useResource(signal => api.receipts({ limit: 10 }, signal), "receipts");
  const facets = useResource(async signal => {
    const [categories, merchants] = await Promise.all([api.categories({ period: "this_year", limit: 100 }, signal), api.merchants({ period: "this_year", limit: 100 }, signal)]);
    return { categories, merchants };
  }, "facets");
  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setFilters(Object.fromEntries(Array.from(data.entries()).filter(([, value]) => String(value).trim() !== "").map(([key, value]) => [key, String(value).trim()])));
    setOffset(0);
  }
  const processing = receipts.data?.filter(item => item.status !== "PROCESSED" && item.status !== "PENDING_UPLOAD") ?? [];
  return <><PageHeader eyebrow="PURCHASE MEMORY" title="Every purchase, remembered." description="The big shops, the small essentials, and all the details in between." />
    <form className="filter-panel" onSubmit={filter}><label className="search-field"><Icon name="search" /><input name="query" maxLength={200} type="search" placeholder="Search a shop or something you bought" aria-label="Search purchases" /></label><div className="filter-fields"><label>From<input type="date" name="start_date" /></label><label>Before<input type="date" name="end_date" /></label><label>Category<select name="category_id"><option value="">All categories</option>{Array.from(new Map((facets.data?.categories.groups ?? []).filter(row => row.category_id).map(row => [row.category_id!, row])).values()).map(row => <option key={row.category_id} value={row.category_id!}>{row.category_name}</option>)}</select></label><label>Merchant<select name="merchant_id"><option value="">All merchants</option>{Array.from(new Map((facets.data?.merchants.groups ?? []).filter(row => row.merchant_id).map(row => [row.merchant_id!, row])).values()).map(row => <option key={row.merchant_id} value={row.merchant_id!}>{row.merchant_name}</option>)}</select></label><label>Payment<select name="payment_status"><option value="">Any status</option><option value="PAID">Paid</option><option value="PARTIALLY_PAID">Partially paid</option><option value="UNPAID">Unpaid</option><option value="UNKNOWN">Unknown</option></select></label><button className="button primary" type="submit">Apply filters</button><button className="text-button" type="reset" onClick={() => { setFilters({}); setOffset(0); }}>Reset</button></div><p className="caption">Use both dates; “Before” excludes that day. Category and merchant choices come from this year’s recorded history; text search covers all matching purchases.</p>{facets.error && <p className="help-text">Filter choices couldn’t load. You can still search by text or dates. <button type="button" className="text-button" onClick={facets.refresh}>Retry choices</button></p>}</form>
    <section className="section"><div className="section-heading"><h2>Purchase history</h2><button className="icon-button" aria-label="Refresh purchases" onClick={() => { list.refresh(); receipts.refresh(); }}><Icon name="refresh" size={18} /></button></div>{list.loading ? <Loading /> : list.error ? <ErrorState message={list.error} retry={list.refresh} /> : list.data?.length ? <><PurchaseList purchases={list.data} /><Pager offset={offset} count={list.data.length} onChange={setOffset} /></> : <><EmptyState title={Object.keys(filters).length || offset ? "No purchases match these filters" : "Your story starts with a receipt"} action={<AddReceipt />}>{Object.keys(filters).length || offset ? "Try a different search or reset your filters." : "Add your first receipt. We’ll keep the details organized for you."}</EmptyState>{offset > 0 && <Pager offset={offset} count={0} onChange={setOffset} />}</>}</section>
    {receipts.error && <ErrorState message={"Receipt processing could not load. " + receipts.error} retry={receipts.refresh} />}
    {processing.length > 0 && <section className="section"><div className="section-heading"><h2>Recent receipt processing</h2><span className="caption">Latest uploads</span></div>{processing.map(receipt => <button className="receipt-row" key={receipt.id} onClick={() => setSelected(receipt)}><Icon name="file" /><strong>{receipt.original_filename}</strong><Status value={receipt.status} /><Icon name="chevron" size={16} /></button>)}</section>}
    {selected && <Modal title="Receipt processing" onClose={() => setSelected(null)}><ReceiptProgress initial={selected} onNavigate={() => setSelected(null)} /></Modal>}</>;
}
