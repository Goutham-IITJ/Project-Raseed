"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useSession } from "../app-provider";
import { Icon } from "../icon";
import { ErrorState, Loading, Modal, PageHeader, Status } from "../ui";
import { WalletActions } from "./wallet";
import { useResource } from "@/lib/use-resource";
import { dateTime, decimal, money } from "@/lib/format";
function ReceiptViewer({ id }: { id: string }) {
  const { api } = useSession();
  const file = useResource(signal => api.receiptFile(id, signal), id);
  const [object, setObject] = useState<{ blob: Blob; url: string }>();
  useEffect(() => {
    if (!file.data) return;
    const url = URL.createObjectURL(file.data);
    // The asynchronous state update belongs to the external blob resource lifecycle.
    Promise.resolve().then(() => setObject({ blob: file.data!, url }));
    return () => URL.revokeObjectURL(url);
  }, [file.data]);
  if (file.error) return <ErrorState message={file.error} retry={file.refresh} />;
  if (!object || object.blob !== file.data) return <Loading />;
  return <div className="receipt-viewer">{object.blob.type.startsWith("image/") ? <Image src={object.url} alt="Your original uploaded receipt" width={1200} height={1600} unoptimized style={{ width: "100%", height: "auto" }} /> : <iframe src={object.url} title="Original receipt PDF" />}<a className="button secondary" download="receipt" href={object.url}>Download original<Icon name="external" size={16} /></a></div>;
}
export function PurchaseDetail({ id }: { id: string }) {
  const { api, profile } = useSession();
  const purchase = useResource(signal => api.purchase(id, signal), id);
  const passes = useResource(signal => api.passes({ purchase_id: id }, signal), "pass:" + id);
  const [viewReceipt, setViewReceipt] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  if (purchase.loading) return <Loading />;
  if (purchase.error || !purchase.data) return <ErrorState message={purchase.error} retry={purchase.refresh} />;
  const item = purchase.data;
  const ensureWallet = async () => { setBusy(true); setError(undefined); try { await api.ensurePass(id); passes.refresh(); } catch (cause) { setError((cause as Error).message); } finally { setBusy(false); } };
  return <><Link href="/purchases" className="back-link"><Icon name="back" size={17} />Purchase history</Link><PageHeader eyebrow="PURCHASE DETAILS" title={item.merchant_name_raw} description={dateTime(item.purchased_at, profile.locale, profile.timezone, true)} actions={<Status value={item.payment_status} />} />
    <div className="detail-layout"><section className="section purchase-detail"><div className="purchase-total"><span>Total purchase</span><strong>{money(item.grand_total, item.currency, profile.locale)}</strong><small>Recorded from your purchase · {item.currency}</small></div><div className="section-heading"><h2>What you bought</h2><span className="caption">{item.line_items.length} recorded items</span></div>{item.line_items.length ? <div className="table-scroll"><table><thead><tr><th>Item</th><th>Quantity</th><th>Unit price</th><th>Line total</th></tr></thead><tbody>{item.line_items.map(line => <tr key={line.id}><td>{line.raw_name}</td><td>{decimal(line.quantity)} {line.unit}</td><td>{money(line.unit_price, item.currency, profile.locale)}</td><td>{money(line.line_total, item.currency, profile.locale)}</td></tr>)}</tbody></table></div> : <p className="muted">No individual line items were recorded.</p>}<p className="caption">Unknown amounts stay unfilled. Item totals may not include all purchase charges.</p><dl className="totals">{[["Subtotal", item.subtotal], ["Discount", item.discount_total], ["Tax", item.tax_total], ["Shipping", item.shipping_total]].map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{money(value, item.currency, profile.locale)}</dd></div>)}</dl>{item.notes && <div className="purchase-notes"><h3>Notes</h3><p>{item.notes}</p></div>}</section><aside><section className="section"><div className="section-heading"><h2>Payment</h2><Icon name="wallet" /></div>{item.payments.length ? item.payments.map(payment => <div className="payment-row" key={payment.id}><strong>{payment.method}{payment.last4 ? " · " + payment.last4 : ""}</strong><span>{money(payment.amount, payment.currency, profile.locale)}</span></div>) : <p className="muted">No payment details were recorded. The purchase status appears above.</p>}</section><section className="section"><div className="section-heading"><h2>Original receipt</h2><Icon name="file" /></div><p className="muted">The original details, kept close.</p>{item.receipt_id ? <button className="button secondary full" onClick={() => setViewReceipt(true)}>View receipt<Icon name="external" size={16} /></button> : <p className="caption">No receipt is linked to this purchase.</p>}</section><section className="section"><div className="section-heading"><h2>Keep it in Wallet</h2><Icon name="wallet" /></div>{passes.loading ? <Loading compact /> : passes.error ? <ErrorState message={passes.error} retry={passes.refresh} /> : passes.data?.[0] ? <WalletActions pass={passes.data[0]} onChange={passes.refresh} /> : <button className="button secondary full" disabled={busy} onClick={() => void ensureWallet()}>{busy ? "Preparing…" : "Prepare Wallet pass"}</button>}{error && <ErrorState message={error} />}</section><Link href="/assistant" className="text-link">Ask about your purchases<Icon name="arrow" size={16} /></Link></aside></div>{viewReceipt && item.receipt_id && <Modal title="Original receipt" wide onClose={() => setViewReceipt(false)}><ReceiptViewer id={item.receipt_id} /></Modal>}</>;
}
