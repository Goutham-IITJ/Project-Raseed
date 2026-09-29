"use client";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession } from "./app-provider";
import { Icon, type IconName } from "./icon";
import { Modal } from "./ui";
import { ReceiptUpload } from "./upload";
const navigation: { href: string; label: string; icon: IconName }[] = [
  { href: "/", label: "Overview", icon: "overview" }, { href: "/purchases", label: "Purchases", icon: "receipt" }, { href: "/inventory", label: "Inventory", icon: "inventory" }, { href: "/insights", label: "Insights", icon: "insights" }, { href: "/assistant", label: "Assistant", icon: "assistant" }, { href: "/wallet", label: "Wallet", icon: "wallet" }, { href: "/settings", label: "Settings", icon: "settings" },
];
export function AddReceipt({ className = "button primary" }: { className?: string }) {
  const [open, setOpen] = useState(false);
  return <><button className={className} onClick={() => setOpen(true)}><Icon name="plus" size={18} />Add Receipt</button>{open && <Modal title="Add a receipt" onClose={() => setOpen(false)}><ReceiptUpload onNavigate={() => setOpen(false)} /></Modal>}</>;
}
export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { profile } = useSession();
  const [mobile, setMobile] = useState(false);
  const links = <nav aria-label="Main navigation">{navigation.map(item => { const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href); return <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined} onClick={() => setMobile(false)}><Icon name={item.icon} /><span>{item.label}</span>{active && <span className="nav-dot" />}</Link>; })}</nav>;
  const brand = <Link href="/" className="brand"><span className="brand-mark"><Icon name="receipt" size={22} /></span>raseed<span className="brand-dot">.</span></Link>;
  return <div className="app"><a className="skip-link" href="#main">Skip to content</a><aside className="sidebar">{brand}<p className="sidebar-caption">YOUR EVERYDAY, ORGANIZED</p>{links}<div className="sidebar-bottom"><div className="sidebar-note"><Icon name="leaf" /><p>Less searching.<br /><strong>More living.</strong></p></div><Link href="/settings" className="account"><span className="avatar">{(profile.display_name ?? profile.email ?? "R").slice(0, 1).toUpperCase()}</span><span><strong>{profile.display_name ?? "Your account"}</strong><small>Personal space</small></span><Icon name="chevron" size={16} /></Link></div></aside><div className="workspace"><header className="topbar"><div className="topbar-left"><button className="icon-button mobile-toggle" aria-label="Open navigation" aria-expanded={mobile} onClick={() => setMobile(true)}><Icon name="menu" /></button><span className="topbar-label">Your purchase memory</span></div><AddReceipt /></header><main id="main" className="page" tabIndex={-1}>{children}</main><footer className="app-footer"><span>Raseed · A little clarity, every day.</span><span><Icon name="shield" size={13} /> Private by design</span></footer></div>{mobile && <Modal title="Your Raseed" onClose={() => setMobile(false)}><div className="mobile-nav">{links}</div></Modal>}</div>;
}
