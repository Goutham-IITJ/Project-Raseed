"use client";
import { useState } from "react";
import Link from "next/link";
import { useSession } from "../app-provider";
import { Icon } from "../icon";
import { EmptyState, ErrorState, Loading, PageHeader, Pager, Status } from "../ui";
import { useResource } from "@/lib/use-resource";
import { walletUrl } from "@/lib/client";
import { dateTime, money } from "@/lib/format";
import type { WalletPass } from "@/lib/types";
export function WalletActions({ pass, onChange }: { pass: WalletPass; onChange: () => void }) {
  const { api, profile, demo } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  async function act(save: boolean) {
    setBusy(true); setError(undefined);
    try {
      if (save) { const result = await api.savePass(pass.id); window.location.assign(walletUrl(result.save_url)); }
      else { await api.syncPass(pass.id); onChange(); }
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="wallet-actions"><Status value={pass.status} />{pass.status === "SYNCED" ? <><button className="button wallet-save" disabled={busy || demo} onClick={() => void act(true)}><Icon name="wallet" size={17} />{busy ? "Opening…" : "Add to Google Wallet"}</button><p className="caption">{demo ? "Sample pass · no pass was issued to Google." : "Synced with Google. Save to add it to your Wallet."}</p><button className="text-button" disabled={busy || demo} onClick={() => void act(false)}>Refresh pass details</button></> : pass.status === "FAILED" ? <><p className="help-text">Sync failed. Retry to prepare this pass.</p><button className="button secondary" disabled={busy || demo} onClick={() => void act(false)}><Icon name="refresh" size={16} />{busy ? "Queuing…" : "Retry synchronization"}</button></> : <><p className="muted">{pass.status === "RETRY" ? "Another attempt is scheduled for " + dateTime(pass.next_attempt_at, profile.locale, profile.timezone, true) + "." : "Waiting for synchronization."}</p><button className="text-button" disabled={busy || demo} onClick={onChange}><Icon name="refresh" size={15} />Check status</button></>}{error && <ErrorState message={error} />}</div>;
}
export function Wallet() {
  const { api } = useSession();
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const passes = useResource(signal => api.passes({ status, offset, limit: 20 }, signal), status + offset);
  return <><PageHeader title="Wallet" actions={<label className="select-label"><span className="sr-only">Wallet status</span><select value={status} onChange={event => { setStatus(event.target.value); setOffset(0); }}><option value="">All passes</option><option value="SYNCED">Ready to save</option><option value="PENDING">Pending</option><option value="SYNCING">Preparing</option><option value="RETRY">Retry scheduled</option><option value="FAILED">Needs attention</option></select></label>} /><div className="wallet-intro"><span className="wallet-emblem"><Icon name="wallet" size={30} /></span><div><h2>Purchase passes</h2><p>Save a copy to Google Wallet.</p></div><Icon name="arrow" size={24} /></div>{passes.loading ? <Loading /> : passes.error ? <ErrorState message={passes.error} retry={passes.refresh} /> : passes.data?.length ? <><div className="wallet-grid">{passes.data.map(pass => <WalletCard key={pass.id} pass={pass} onChange={passes.refresh} />)}</div><Pager offset={offset} count={passes.data.length} onChange={setOffset} /></> : <section className="section"><EmptyState icon="wallet" title="No passes in this view" action={<Link href="/purchases" className="button secondary">Explore purchases<Icon name="arrow" size={17} /></Link>}>Open a purchase to prepare a Wallet pass.</EmptyState><Pager offset={offset} count={0} onChange={setOffset} /></section>}</>;
}

function WalletCard({ pass, onChange }: { pass: WalletPass; onChange: () => void }) {
  const { api, profile } = useSession();
  const purchase = useResource(signal => api.purchase(pass.purchase_id, signal), pass.purchase_id);
  return <article className={"wallet-card wallet-" + pass.status.toLowerCase()}><div className="wallet-preview"><div className="wallet-preview-top"><Icon name="receipt" size={22} /><span>RASEED PURCHASE PASS</span><Icon name={pass.status === "SYNCED" ? "check" : pass.status === "FAILED" ? "warning" : "clock"} size={19} /></div>{purchase.loading ? <Loading compact /> : purchase.error ? <ErrorState message={purchase.error} retry={purchase.refresh} /> : purchase.data && <><h2>{purchase.data.merchant_name_raw}</h2><strong className="wallet-amount">{money(purchase.data.grand_total, purchase.data.currency, profile.locale)}</strong><small>{dateTime(purchase.data.purchased_at, profile.locale, profile.timezone)}</small></>}<Link href={"/purchases/" + pass.purchase_id} className="text-link">View purchase<Icon name="arrow" size={16} /></Link></div><div className="wallet-card-body"><WalletActions pass={pass} onChange={onChange} />{pass.synced_at && <small className="caption">Last synced {dateTime(pass.synced_at, profile.locale, profile.timezone)}</small>}</div></article>;
}
