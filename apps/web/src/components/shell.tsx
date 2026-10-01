"use client";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession } from "./app-provider";
import { Icon, type IconName } from "./icon";
import { Modal } from "./ui";
import { ReceiptUpload } from "./upload";

const navigation: { href: string; label: string; icon: IconName }[] = [
  { href: "/", label: "Overview", icon: "overview" },
  { href: "/purchases", label: "Purchases", icon: "receipt" },
  { href: "/analysis", label: "Analysis", icon: "analysis" },
  { href: "/inventory", label: "Inventory", icon: "inventory" },
  { href: "/insights", label: "Insights", icon: "insights" },
  { href: "/assistant", label: "Assistant", icon: "assistant" },
  { href: "/wallet", label: "Wallet", icon: "wallet" },
  { href: "/settings", label: "Settings", icon: "settings" },
];
export function AddReceipt({ className = "button primary" }: { className?: string }) {
  const [open, setOpen] = useState(false);
  return <><button className={className} onClick={() => setOpen(true)}><Icon name="plus" size={18} />Add Receipt</button>{open && <Modal title="Add a receipt" onClose={() => setOpen(false)}><ReceiptUpload onNavigate={() => setOpen(false)} /></Modal>}</>;
}
export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { profile, demo } = useSession();
  const [mobile, setMobile] = useState(false);
  const current = navigation.find(item => item.href === "/" ? pathname === "/" : pathname.startsWith(item.href));
  const links = <nav aria-label="Main navigation">{navigation.map(item => {
    const active = current?.href === item.href;
    return <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined} onClick={() => setMobile(false)}><Icon name={item.icon} /><span>{item.label}</span>{active && <Icon name="arrow" size={15} />}</Link>;
  })}</nav>;
  return <div className="app"><a className="skip-link" href="#main">Skip to content</a>
    <aside className="sidebar"><Link href="/" className="brand"><span className="brand-mark"><Icon name="receipt" size={23} /></span>raseed<span className="brand-dot">.</span></Link>{links}
      <div className="sidebar-bottom"><Link href="/settings" className="account"><span className="avatar">{(profile.display_name ?? profile.email ?? "R").slice(0, 1).toUpperCase()}</span><span><strong>{profile.display_name ?? "Your account"}</strong><small>Personal account</small></span><Icon name="chevron" size={16} /></Link></div>
    </aside>
    <div className="workspace">{demo && <div className="demo-banner" role="note"><strong>Local demo · Synthetic data</strong><span>Uploads stay queued. Live chat and Wallet actions are unavailable.</span></div>}
      <header className="topbar"><div className="topbar-left"><button className="icon-button mobile-toggle" aria-label="Open navigation" aria-expanded={mobile} onClick={() => setMobile(true)}><Icon name="menu" /></button><span className="topbar-label">Personal <span>/</span> <strong>{current?.label ?? "Raseed"}</strong></span></div><div className="topbar-actions"><Link href="/assistant" className="topbar-assistant"><Icon name="spark" size={17} />Ask Raseed</Link><AddReceipt /></div></header>
      <main id="main" className="page" tabIndex={-1}>{children}</main>
    </div>
    <nav className="bottom-nav" aria-label="Quick navigation">{navigation.filter(item => ["/", "/purchases", "/analysis", "/assistant"].includes(item.href)).map(item => <Link key={item.href} href={item.href} aria-current={current?.href === item.href ? "page" : undefined}><Icon name={item.icon} size={21} /><span>{item.label}</span></Link>)}</nav>
    {mobile && <Modal title="Your Raseed" onClose={() => setMobile(false)}><div className="mobile-nav">{links}</div></Modal>}
  </div>;
}
