"use client";
import { createContext, useContext, useMemo, type ReactNode } from "react";
import Link from "next/link";
import { RaseedApi } from "@/lib/client";
import type { RaseedUser } from "@/lib/api";
import { useIdentity } from "@/lib/use-identity";
import { Icon } from "./icon";
import { ErrorState } from "./ui";
export interface AppSession { demo?: boolean; api: RaseedApi; profile: RaseedUser; logout: () => Promise<void>; reload: () => Promise<void> }
export const SessionContext = createContext<AppSession | null>(null);
export function useSession() { const value = useContext(SessionContext); if (!value) throw new Error("Session required"); return value; }
export function AppProvider({ children }: { children: ReactNode }) {
  const identity = useIdentity();
  const api = useMemo(() => new RaseedApi(identity.getToken), [identity.getToken]);
  if (!identity.profile) return <main className="welcome"><Link className="brand" href="/"><span className="brand-mark"><Icon name="receipt" size={24} /></span>raseed<span className="brand-dot">.</span></Link><div className="welcome-grid"><section><p className="eyebrow">A little less to remember</p><h1>Your purchases.<br />A clearer <em>picture.</em></h1><p className="welcome-copy">From everyday receipts to useful answers. Keep your spending, purchases and household essentials in one thoughtful place.</p>{identity.loading ? <p role="status" className="muted">Getting your account ready…</p> : <><button className="button primary large" disabled={!identity.ready || identity.busy} onClick={() => void (identity.signedIn ? identity.reload() : identity.login())}>{identity.demo ? "Enter local demo" : identity.signedIn ? "Reconnect your account" : "Continue with Google"}<Icon name="arrow" /></button><p className="caption"><Icon name="shield" size={14} /> Your receipts stay private to your account.</p></>}{identity.error && <ErrorState message={identity.error} />}</section><div className="welcome-art" aria-hidden="true"><div className="art-orbit orbit-one" /><div className="art-orbit orbit-two" /><div className="paper"><Icon name="leaf" size={35} /><span>Life, remembered.</span><i /><i /><i /><div className="paper-bottom"><Icon name="check" /> One receipt at a time</div></div><div className="art-label"><Icon name="spark" /> A little clarity, every day</div></div></div><footer>Capture. Understand. Remember.</footer></main>;
  return <SessionContext.Provider key={identity.profile.id} value={{ demo: identity.demo, api, profile: identity.profile, logout: identity.logout, reload: identity.reload }}>{children}</SessionContext.Provider>;
}
