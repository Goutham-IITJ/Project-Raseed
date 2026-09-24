"use client";

import { useIdentity } from "@/lib/use-identity";

export function IdentityCard() {
  const identity = useIdentity();
  const { profile } = identity;
  return (
    <section className="card" aria-labelledby="account-title">
      <div className="eyebrow">Your account</div>
      <h1 id="account-title">{profile ? `Hello, ${profile.display_name ?? "there"}.` : "Welcome to Raseed."}</h1>
      {identity.loading && <p role="status">Loading your account…</p>}
      {!identity.loading && !identity.signedIn && <p>Sign in with Google to create or access your account.</p>}
      {profile && (
        <dl>
          <dt>Email</dt><dd>{profile.email ?? "Not provided"}</dd>
          <dt>Currency</dt><dd>{profile.currency}</dd>
          <dt>Timezone</dt><dd>{profile.timezone}</dd>
          <dt>Locale</dt><dd>{profile.locale}</dd>
        </dl>
      )}
      {identity.error && <p role="alert" className="error">{identity.error}</p>}
      <div className="actions">
        {identity.signedIn ? (
          <>
            <button className="secondary" disabled={identity.busy} onClick={() => void identity.logout()}>Sign out</button>
            {identity.error && <button disabled={identity.loading} onClick={() => void identity.reload()}>Try again</button>}
          </>
        ) : (
          <button disabled={!identity.ready || identity.busy || identity.loading} onClick={() => void identity.login()}>
            {identity.busy ? "Signing in…" : "Continue with Google"}
          </button>
        )}
      </div>
    </section>
  );
}
