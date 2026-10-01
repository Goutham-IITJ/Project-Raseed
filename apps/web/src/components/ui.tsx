"use client";
import { useEffect, useId, useRef, type ReactNode } from "react";
import Link from "next/link";
import { Icon, type IconName } from "./icon";
import { label } from "@/lib/format";
export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return <header className="page-heading"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h1>{title}</h1>{description && <p className="lede">{description}</p>}</div>{actions && <div className="heading-actions">{actions}</div>}</header>;
}
export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "green" | "amber" | "red" }) { return <span className={"badge badge-" + tone}>{children}</span>; }
export function Status({ value }: { value: string }) {
  const tone = ["SYNCED", "PROCESSED", "PAID", "COMPLETED", "NOT_DUE"].includes(value) ? "green" : ["FAILED", "PAST_DUE"].includes(value) ? "red" : ["NEEDS_REVIEW", "DUE", "RETRY", "PROCESSING", "SYNCING", "UPLOADED"].includes(value) ? "amber" : "neutral";
  return <Badge tone={tone}>{label(value)}</Badge>;
}
export function ErrorState({ message, retry }: { message?: string; retry?: () => void }) {
  return <div className="error-state" role="alert"><Icon name="warning" /><div><strong>We couldn’t complete that request</strong><p>{message ?? "Please try again in a moment."}</p>{retry && <button className="text-button" onClick={retry}>Try again <Icon name="refresh" size={15} /></button>}</div></div>;
}
export function EmptyState({ icon = "receipt", title, children, action }: { icon?: IconName; title: string; children: ReactNode; action?: ReactNode }) {
  return <div className="empty-state"><span className="empty-icon"><Icon name={icon} size={28} /></span><h2>{title}</h2><p>{children}</p>{action}</div>;
}
export function Loading({ compact = false }: { compact?: boolean }) {
  return <div className={"skeleton-block " + (compact ? "compact" : "")} role="status" aria-label="Loading"><span className="sr-only">Loading your information…</span><i /><i /><i /></div>;
}
export function Section({ title, href, link = "View all", children, className = "" }: { title: string; href?: string; link?: string; children: ReactNode; className?: string }) {
  return <section className={"section " + className}><div className="section-heading"><h2>{title}</h2>{href && <Link className="text-link" href={href}>{link}<Icon name="arrow" size={16} /></Link>}</div>{children}</section>;
}
export function Pager({ offset, count, size = 20, onChange }: { offset: number; count: number; size?: number; onChange: (value: number) => void }) {
  if (!offset && count < size) return null;
  return <nav className="pagination" aria-label="Results pages"><button className="button secondary" disabled={!offset} onClick={() => onChange(Math.max(0, offset - size))}><Icon name="back" size={16} />Previous</button><span>Page {Math.floor(offset / size) + 1}</span><button className="button secondary" disabled={count < size || offset + size > 10000} onClick={() => onChange(offset + size)}>Next<Icon name="arrow" size={16} /></button></nav>;
}
export function Modal({ title, children, onClose, wide = false }: { title: string; children: ReactNode; onClose: () => void; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current; const previous = document.activeElement as HTMLElement | null;
    dialog?.showModal(); const overflow = document.body.style.overflow; document.body.style.overflow = "hidden";
    return () => { dialog?.close(); document.body.style.overflow = overflow; previous?.focus(); };
  }, []);
  return <dialog ref={ref} className={"modal " + (wide ? "modal-wide" : "")} aria-labelledby={titleId} onCancel={event => { event.preventDefault(); onClose(); }}><div className="modal-heading"><h2 id={titleId}>{title}</h2><button className="icon-button" aria-label="Close dialog" onClick={onClose}><Icon name="close" /></button></div>{children}</dialog>;
}
export function Evidence({ value }: { value: unknown }) {
  if (value == null) return <span className="muted">Not recorded</span>;
  if (Array.isArray(value)) return <div className="evidence-array">{value.length ? value.map((item, i) => <Evidence key={i} value={item} />) : <span className="muted">No records</span>}</div>;
  if (typeof value === "object") return <dl className="evidence-grid">{Object.entries(value).map(([key, item]) => <div key={key}><dt>{label(key)}</dt><dd><Evidence value={item} /></dd></div>)}</dl>;
  return <span>{String(value)}</span>;
}
