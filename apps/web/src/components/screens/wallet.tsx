"use client";
import { useState } from "react";
import Link from "next/link";
import { useSession } from "../app-provider";
import { Icon } from "../icon";
import { EmptyState, ErrorState, Loading, PageHeader, Pager, Status } from "../ui";
import { useResource } from "@/lib/use-resource";
import { walletUrl } from "@/lib/client";
import { dateTime } from "@/lib/format";
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
  return <div className="wallet-actions"><Status value={pass.status} />{pass.status === "SYNCED" ? <><button className="button wallet-save" disabled={busy || demo} onClick={() => void act(true)}><span className="google-g" aria-hidden="true">G</span>{busy ? "Opening…" : "Add to Google Wallet"}</button><p className="caption">Ready to save. Google Wallet confirms the final addition.</p><button className="text-button" disabled={busy || demo} onClick={() => void act(false)}>Refresh pass details</button></> : pass.status === "FAILED" ? <><p className="help-text">This pass couldn’t be prepared. Your purchase is still safely stored in Raseed.</p><button className="button secondary" disabled={busy || demo} onClick={() => void act(false)}><Icon name="refresh" size={16} />{busy ? "Queuing…" : "Retry synchronization"}</button></> : <><p className="muted">{pass.status === "RETRY" ? "Another attempt is scheduled for " + dateTime(pass.next_attempt_at, profile.locale, profile.timezone, true) + "." : "Your pass is being prepared. You can return to it later."}</p><button className="text-button" disabled={busy || demo} onClick={onChange}><Icon name="refresh" size={15} />Check status</button></>}{error && <ErrorState message={error} />}</div>;
}
export function Wallet() {
  const { api, profile } = useSession();
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const passes = useResource(signal => api.passes({ status, offset, limit: 20 }, signal), status + offset);
  return <><PageHeader eyebrow="READY WHEN YOU NEED IT" title="Your purchases, to go." description="Keep a convenient copy of your purchase details in Google Wallet." actions={<label className="select-label"><span className="sr-only">Wallet status</span><select value={status} onChange={event => { setStatus(event.target.value); setOffset(0); }}><option value="">All passes</option><option value="SYNCED">Ready to save</option><option value="PENDING">Pending</option><option value="SYNCING">Preparing</option><option value="RETRY">Retry scheduled</option><option value="FAILED">Needs attention</option></select></label>} /><div className="wallet-intro"><Icon name="wallet" size={32} /><p>Your purchase memory lives in Raseed.<br /><strong>Wallet keeps a handy copy close by.</strong></p></div>{passes.loading ? <Loading /> : passes.error ? <ErrorState message={passes.error} retry={passes.refresh} /> : passes.data?.length ? <><div className="wallet-grid">{passes.data.map((pass, index) => <article className="wallet-card" key={pass.id}><div className={"wallet-preview tint-" + index % 3}><span className="brand">raseed.</span><Icon name="receipt" size={45} /><span>Purchase memory</span><Link href={"/purchases/" + pass.purchase_id} className="text-link">View purchase<Icon name="arrow" size={16} /></Link></div><div className="wallet-card-body"><WalletActions pass={pass} onChange={passes.refresh} />{pass.synced_at && <small className="caption">Last synchronized {dateTime(pass.synced_at, profile.locale, profile.timezone)}</small>}</div></article>)}</div><Pager offset={offset} count={passes.data.length} onChange={setOffset} /></> : <section className="section"><EmptyState icon="wallet" title="Your wallet is waiting" action={<Link href="/purchases" className="button secondary">Explore purchases<Icon name="arrow" size={17} /></Link>}>Passes are prepared from recorded purchases. Open a purchase to prepare its pass, or check back after synchronization.</EmptyState><Pager offset={offset} count={0} onChange={setOffset} /></section>}</>;
}
