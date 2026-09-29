"use client";
import { useState, useRef, type FormEvent } from "react";
import Link from "next/link";
import { useSession } from "../app-provider";
import { Icon } from "../icon";
import { Badge, EmptyState, ErrorState, Loading, Modal, PageHeader, Pager, Status } from "../ui";
import { useResource } from "@/lib/use-resource";
import { dateTime, decimal, label } from "@/lib/format";
import type { InventoryCommand, Lot } from "@/lib/types";
export function Inventory() {
  const { api } = useSession();
  const [offset, setOffset] = useState(0);
  const items = useResource(signal => api.items({ limit: 20, offset }, signal), String(offset));
  const lots = useResource(signal => api.lots({ limit: 100 }, signal), "attention");
  const attention = lots.data?.filter(lot => ["DUE", "PAST_DUE"].includes(lot.expiry.status) && decimal(lot.quantity_remaining) !== "0") ?? [];
  return <><PageHeader eyebrow="AT HOME, IN MIND" title="Know what you have." description="Keep everyday essentials in view, and make a little more of what’s already there." />
    {attention.length > 0 && <div className="attention-strip"><Icon name="clock" /><div><strong>Some recorded lots need attention</strong><p>{attention.slice(0, 3).map(lot => lot.name).join(", ")}. Check their recorded expiry before use.</p><small>Based on the latest 100 lots; expiry does not mean an item has been consumed.</small></div></div>}
    <section className="section"><div className="section-heading"><h2>Your inventory</h2><button className="icon-button" aria-label="Refresh inventory" onClick={() => { items.refresh(); lots.refresh(); }}><Icon name="refresh" size={18} /></button></div>{items.loading ? <Loading /> : items.error ? <ErrorState message={items.error} retry={items.refresh} /> : items.data?.length ? <><div className="inventory-list">{items.data.map(item => <Link className="inventory-row" href={"/inventory/" + item.id} key={item.id}><span className="soft-icon"><Icon name="inventory" /></span><div><strong>{item.name}</strong><small>{item.lot_count} recorded {item.lot_count === 1 ? "lot" : "lots"}</small></div><span className="quantity"><strong>{decimal(item.quantity_remaining)}</strong> {item.unit}</span>{decimal(item.quantity_remaining) === "0" && <Badge>Depleted</Badge>}<Icon name="chevron" size={17} /></Link>)}</div><Pager offset={offset} count={items.data.length} onChange={setOffset} /></> : <><EmptyState icon="inventory" title="A little space for your essentials" action={<Link href="/purchases" className="button secondary">Explore purchases<Icon name="arrow" size={16} /></Link>}>Eligible purchases become inventory after processing. Quantities reflect recorded activity, so you can keep them up to date.</EmptyState><Pager offset={offset} count={0} onChange={setOffset} /></>}</section>{lots.error && <ErrorState message={"Inventory attention couldn’t load. " + lots.error} retry={lots.refresh} />}<p className="data-note">Inventory quantities are derived from recorded purchases and actions. Estimated or external expiry evidence is always labeled.</p></>;
}
function LotAction({ lot, onSaved, onClose }: { lot: Lot; onSaved: () => void; onClose: () => void }) {
  const { api } = useSession();
  const [kind, setKind] = useState<InventoryCommand["event_type"]>("CONSUMED");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const command = useRef<{ signature: string; key: string } | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    const quantity = String(form.get("quantity")).trim();
    const reason = String(form.get("reason")).trim();
    const body = { expected_version: lot.version, event_type: kind, reason, ...(kind === "CORRECTION" ? { quantity_remaining: quantity } : { quantity }) };
    const signature = JSON.stringify(body);
    if (command.current?.signature !== signature) command.current = { signature, key: crypto.randomUUID() };
    setBusy(true); setError(undefined);
    try { await api.inventoryAction(lot.id, { ...body, idempotency_key: command.current.key }); onSaved(); onClose(); }
    catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  return <form onSubmit={event => void submit(event)} className="stack-form"><p>Update <strong>{lot.name}</strong>. Recorded quantity: <strong>{decimal(lot.quantity_remaining)} {lot.unit}</strong>.</p><label>Action<select value={kind} onChange={event => setKind(event.target.value as InventoryCommand["event_type"])} disabled={busy}><option value="CONSUMED">Used / consumed</option><option value="DISCARDED">Discarded</option><option value="CORRECTION">Correct remaining quantity</option></select></label><label>{kind === "CORRECTION" ? "Actual quantity remaining" : "Quantity used or discarded"} ({lot.unit})<input name="quantity" inputMode="decimal" pattern="[0-9]+(\.[0-9]{1,6})?" required maxLength={21} placeholder={kind === "CORRECTION" ? "0" : "1"} disabled={busy} /></label><label>Reason<input name="reason" required maxLength={500} placeholder="For example, used one package" disabled={busy} /></label><p className="help-text">This adds an activity record. Your original purchase stays unchanged.</p>{error && <ErrorState message={error} />}<div className="actions"><button className="button primary" disabled={busy}>{busy ? "Recording…" : kind === "DISCARDED" ? "Record discard" : "Record update"}</button><button className="button secondary" type="button" disabled={busy} onClick={onClose}>Cancel</button></div></form>;
}
function LotHistory({ lot }: { lot: Lot }) {
  const { api, profile } = useSession();
  const [offset, setOffset] = useState(0);
  const events = useResource(signal => api.events(lot.id, { limit: 20, offset }, signal), lot.id + offset);
  return <>{events.loading ? <Loading /> : events.error ? <ErrorState message={events.error} retry={events.refresh} /> : <><ol className="activity-list">{events.data?.map(event => <li key={event.id}><span className="activity-dot" /><div><strong>{label(event.event_type)} · {decimal(event.quantity_delta)} {lot.unit}</strong><p>{event.reason}</p><small>{dateTime(event.created_at, profile.locale, profile.timezone, true)} · {label(event.source)}</small></div></li>)}</ol><Pager offset={offset} count={events.data?.length ?? 0} onChange={setOffset} /></>}</>;
}
export function InventoryDetail({ id }: { id: string }) {
  const { api, profile } = useSession();
  const [offset, setOffset] = useState(0);
  const item = useResource(signal => api.item(id, signal), id);
  const lots = useResource(signal => api.itemLots(id, { limit: 20, offset }, signal), id + offset);
  const [action, setAction] = useState<Lot | null>(null);
  const [history, setHistory] = useState<Lot | null>(null);
  const refresh = () => { item.refresh(); lots.refresh(); };
  return <><Link href="/inventory" className="back-link"><Icon name="back" size={17} />Your inventory</Link>{item.loading ? <Loading /> : item.error ? <ErrorState message={item.error} retry={item.refresh} /> : item.data && <PageHeader eyebrow="INVENTORY DETAILS" title={item.data.name} description={decimal(item.data.quantity_remaining) + " " + item.data.unit + " remaining · derived from recorded activity"} actions={<button className="button secondary" onClick={refresh}><Icon name="refresh" size={16} />Refresh</button>} />}<section className="section"><div className="section-heading"><h2>Purchase lots</h2><span className="caption">Every batch has its own story</span></div>{lots.loading ? <Loading /> : lots.error ? <ErrorState message={lots.error} retry={lots.refresh} /> : lots.data?.length ? <><div className="lot-list">{lots.data.map(lot => <article key={lot.id} className="lot"><div className="lot-heading"><div><p className="eyebrow">ACQUIRED {dateTime(lot.acquired_at, profile.locale, profile.timezone)}</p><h3>{decimal(lot.quantity_remaining)} <span>{lot.unit} remaining</span></h3></div><Status value={lot.expiry.status} /></div><dl className="facts"><div><dt>Originally acquired</dt><dd>{decimal(lot.quantity_acquired)} {lot.unit}</dd></div><div><dt>Recorded expiry</dt><dd>{dateTime(lot.expiry.date, profile.locale)}</dd></div><div><dt>Expiry source</dt><dd>{label(lot.expiry.source)} · {label(lot.expiry.provenance)}</dd></div><div><dt>Source confidence</dt><dd>{lot.expiry.confidence == null ? "Not available" : decimal(lot.expiry.confidence) + " / 1"}</dd></div></dl><div className="actions"><button className="button secondary" onClick={() => setAction(lot)}>Record an update<Icon name="plus" size={16} /></button><button className="text-button" onClick={() => setHistory(lot)}>Activity history</button><Link className="text-link" href={"/purchases/" + lot.purchase_id}>View purchase<Icon name="arrow" size={16} /></Link></div></article>)}</div><Pager offset={offset} count={lots.data.length} onChange={setOffset} /></> : <><EmptyState icon="inventory" title="No lots on this page">Try the previous page or refresh your inventory.</EmptyState><Pager offset={offset} count={0} onChange={setOffset} /></>}</section>{action && <Modal title="Update inventory" onClose={() => setAction(null)}><LotAction lot={action} onSaved={refresh} onClose={() => setAction(null)} /></Modal>}{history && <Modal title="Recorded activity" onClose={() => setHistory(null)}><LotHistory lot={history} /></Modal>}</>;
}
