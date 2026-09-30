# ADR-014 — Development-only local demo

Authorized as a local exploration aid after M10. No new domain model, API,
migration or production authentication mechanism is introduced.

Backend LOCAL_DEMO defaults false; APP_ENV defaults production. Enabling demo
requires APP_ENV=development, a loopback PostgreSQL database ending in _demo,
local storage, loopback HTTP CORS origins, and no recognized hosted runtime.
Requests also require a loopback peer, Host and allowed Origin. The sole accepted
demo bearer value maps to the fixed identity raseed-local-demo-v1, never a supplied
user ID. With demo off, the original Firebase verifier remains unchanged.

The frontend requires NEXT_PUBLIC_LOCAL_DEMO=true and next dev. Production build
and start reject the flag; production client code cannot select demo identity.
A persistent banner identifies synthetic data. The backend remains authoritative
for ownership and computed values. A dedicated database separates samples from
normal accounts. This is a local convenience credential, not a deployment secret.

An explicit CLI seeds existing schemas through domain services and repositories.
The seed uses a transaction, an advisory lock and an immutable purchase marker,
so repeated/concurrent runs preserve edits without duplicate data. Calendar dates
are anchored at first seed; a rerun never silently moves historical records.
Synthetic receipts and provider lifecycle examples are labeled as such. Inventory
balances use events; insight rules and assistant grounding use existing services.

External assistant, market and Wallet HTTP actions and the external worker are
disabled in demo. Saved conversation/Wallet examples make no real provider calls.
Uploads may be stored locally but remain queued. No demo save URL is generated.
Normal production mode retains its existing providers and authentication.
