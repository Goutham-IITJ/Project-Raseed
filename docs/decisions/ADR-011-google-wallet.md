# ADR-011 — Google Wallet purchase projection

## Scope and boundary

M8 implements WalletPass inside the modular monolith. PostgreSQL remains canonical;
Google Wallet is an asynchronous external projection. The legacy adapter informs
only the Google integration, with no legacy code or storage changes. Each canonical
purchase (including manual purchases) has at most one GOOGLE/GENERIC pass. M8 does
not project insights or inventory, invent ticket semantics, or implement M9/UI.

WalletProvider isolates Generic class/object synchronization and signed save links.
The adapter uses the Google Wallet REST API and Application Default Credentials.
IAM Credentials signJwt signs links using a configured service account; no private
key is loaded by application code. Credentials, issuer ID, signer email and allowed
web origins are deployment configuration. Startup and automated tests need none.

## Persistence and delivery

WalletPass has UUID/owner/purchase, fixed provider/type, nullable class/object IDs,
PENDING/SYNCING/RETRY/SYNCED/FAILED status, per-cycle attempt count, availability,
lease token/expiry, safe last error code/time, last successful synchronization and
creation/update times. Owner/purchase composite FKs and purchase/provider/type and
provider/object uniqueness enforce ownership and idempotency. IDs are initially
null when configuration is absent and become immutable once assigned:
`<issuer>.raseed_receipts_v1` and `<issuer>.raseed_purchase_<purchase UUID hex>`.
Changing issuer configuration cannot silently create replacement external objects.

The existing PURCHASE_CREATED outbox gains only wallet_processed_at. A bounded
dispatcher locks source events and atomically inserts missing PENDING WalletPass
rows and acknowledges this handoff. WalletPass is the durable synchronization job;
its lifecycle owns retries independently of inventory/insight delivery. All existing
purchase events are eligible for backfill. Other event kinds are ignored. No new
domain event or queue table is introduced. API requests can ensure the same unique
pass before handoff; subsequent handoff never resets it.

The worker claims a pass in a short transaction, reads an owned canonical purchase
snapshot, then releases all transactions/locks before Google I/O. Only canonical
merchant, timestamp, currency, exact total and payment status are projected; no
receipt URLs/binaries, payment instruments, notes or model output are sent. Exact
amount strings keep six fractional digits and their currency; there is no rounding
or conversion. The pass is a receipt record, not a payment or admission credential.
Google payloads carry no ownership identifiers. SYNCED means the Google API accepted
the projection, not that the user saved it into a Google account.

## Recovery and idempotency

Class insert conflict means the stable class exists. Objects are patched; missing
objects are inserted, with insert conflicts recovered by patching the same ID.
Unknown outcomes and duplicate deliveries therefore converge on one external object.
Google responses never overwrite canonical records. No hidden HTTP retries occur.

Three attempts per cycle use persisted 5/10-second exponential backoff. Transient
transport/timeout/408/429/5xx failures retry; Retry-After (seconds or HTTP date) is
honored up to one day. Invalid responses, validation, authorization and configuration
fail permanently. Safe codes/timestamps are retained, never provider response bodies.
Claims use five-minute leases and random tokens. Expired claims can be reclaimed;
finalization requires the current token and unexpired lease. Exhausted crashes fail
durably. A crash after Google success safely repeats the same object upsert. External
systems cannot honor database fencing tokens; concurrent stale external requests
converge because M8 purchase records are immutable. Future purchase edits require a
revision-aware refresh/reconciliation contract before enabling them.

Authenticated explicit sync requeues SYNCED/FAILED passes with a fresh attempt
budget. PENDING/RETRY/SYNCING requests are idempotent and preserve backoff/leases.
An operator can similarly requeue a failed pass through --retry-wallet. Failed
configuration stays visible until configuration is corrected and a retry requested.

## APIs and issuance

POST /api/v1/wallet/passes accepts only purchase_id and returns 202 with the existing
or newly queued pass. GET collection/detail expose owned status and safe error fields.
POST /{id}/sync accepts an empty object and returns 202. POST /{id}/add-to-wallet
accepts an empty object and requires SYNCED (otherwise 409). All use Firebase ownership,
strict fields/query validation and no-store; missing/foreign IDs return the same 404.

Save links are signed outside database transactions, use iss=the configured signer,
aud=google, typ=savetowallet, iat, a five-minute exp, configured origins, and only the
existing Generic object/class references. The signed URL is returned transiently,
never persisted/logged. Treat it as a bearer capability; expiry is a JWT claim and
Google controls its acceptance. Signing failures return a safe 502/503/504 and do not
change synchronization state or the canonical purchase. Links do not prove saving.

## Migration and validation

0008_google_wallet creates wallet_passes and the independent outbox handoff/index.
Upgrade preserves M1–M7 records and acknowledgements. Downgrade removes M8 local
projection state only; it cannot delete Google objects. Stable IDs allow later
reconstruction. Destructive migration tests use only the disposable test database.
Tests exercise mocked REST/signing, real PostgreSQL ownership, retries, fencing,
crash recovery, atomic handoff, concurrent duplicates and migration preservation.

Managed task deployment, insight passes, ticket-specific passes, save callbacks,
notifications, deletion/revocation, Google account association, M9 and UI are deferred.

Integration references:
- https://developers.google.com/wallet/generic/rest/v1/genericclass
- https://developers.google.com/wallet/generic/rest/v1/genericobject
- https://developers.google.com/wallet/generic/web
- https://cloud.google.com/iam/docs/reference/credentials/rest/v1/projects.serviceAccounts/signJwt
