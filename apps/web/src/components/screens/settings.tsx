"use client";
import { useState, type FormEvent } from "react";
import { useSession } from "../app-provider";
import { Icon } from "../icon";
import { ErrorState, Loading, PageHeader } from "../ui";
import { useResource } from "@/lib/use-resource";
import type { Preferences } from "@/lib/types";
function PreferenceForm({ initial }: { initial: Preferences }) {
  const { api, reload } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [saved, setSaved] = useState(false);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); if (busy) return;
    const form = new FormData(event.currentTarget);
    const data = { currency: String(form.get("currency")).trim().toUpperCase(), timezone: String(form.get("timezone")).trim(), locale: String(form.get("locale")).trim() };
    setBusy(true); setError(undefined); setSaved(false);
    try { await api.savePreferences(data); await reload(); setSaved(true); }
    catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  };
  return <form className="stack-form preference-form" onChange={() => setSaved(false)} onSubmit={event => void submit(event)}><div className="field-grid"><label>Preferred currency<input name="currency" defaultValue={initial.currency} required minLength={3} maxLength={3} pattern="[A-Za-z]{3}" autoCapitalize="characters" /><small>Three-letter code, such as INR, USD or GBP.</small></label><label>Timezone<input name="timezone" defaultValue={initial.timezone} required list="timezones" /><datalist id="timezones"><option>Asia/Kolkata</option><option>America/New_York</option><option>Europe/London</option><option>UTC</option></datalist><small>Controls the calendar periods in your spending history.</small></label><label>Language & region<input name="locale" defaultValue={initial.locale} required list="locales" /><datalist id="locales"><option>en-IN</option><option>en-US</option><option>en-GB</option></datalist><small>Controls date and number presentation.</small></label></div><p className="help-text">Display preferences only. Currencies are not converted.</p>{error && <ErrorState message={error} />}{saved && <p className="success-message" role="status"><Icon name="check" size={18} />Preferences saved.</p>}<button className="button primary" disabled={busy}>{busy ? "Saving…" : "Save preferences"}</button></form>;
}
export function Settings() {
  const { api, profile, logout, reload, demo } = useSession();
  const preferences = useResource(signal => api.preferences(signal), "preferences");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const signout = async () => { setBusy(true); try { await logout(); } catch (cause) { setError((cause as Error).message); } finally { setBusy(false); } };
  return <><PageHeader title="Settings" /><section className="section settings-section"><div className="section-heading"><h2>Account</h2><Icon name="shield" /></div><div className="profile-row"><span className="avatar large">{(profile.display_name ?? profile.email ?? "R").slice(0, 1).toUpperCase()}</span><div><h3>{profile.display_name ?? "Your Raseed account"}</h3><p>{profile.email ?? "Email not provided"}</p><span className="caption">{demo ? "Local demo account · synthetic data" : "Signed in with Google"}</span></div></div></section><section className="section settings-section"><div className="section-heading"><h2>Preferences</h2></div>{preferences.loading ? <Loading /> : preferences.error ? <ErrorState message={preferences.error} retry={preferences.refresh} /> : preferences.data && <PreferenceForm initial={preferences.data} />}</section><section className="section settings-section"><div className="section-heading"><h2>Account session</h2></div><p className="muted">Sign out of this browser.</p><div className="actions"><button className="button secondary" disabled={busy} onClick={() => void signout()}><Icon name="logout" size={17} />{busy ? "Signing out…" : "Sign out"}</button><button className="text-button" onClick={() => void reload()}>Reload account preferences</button></div>{error && <ErrorState message={error} />}</section></>;
}
