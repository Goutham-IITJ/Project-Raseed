# Workflow D — Insights and Wallet

## Insight pipeline

Domain event → Insight evaluation → structured metrics → insight record → explanation generation → optional delivery.

Examples:
- spending change
- unusual spending
- budget progress (future; depends on a later budget-persistence design decision)
- recurring/duplicate patterns
- savings opportunity

## Wallet principle

Google Wallet is a projection of Raseed state, not the canonical source of truth.

Raseed stores the purchase, insight, and synchronization state. A dedicated Wallet integration service translates Raseed state into Google Wallet pass classes/objects and issues or updates them.

## Typical events

PURCHASE_CREATED → receipt Wallet sync / analytics / insight evaluation
INVENTORY_CHANGED → optional Wallet projection refresh
INSIGHT_CREATED → optional insight pass update

## Failure handling

Wallet failures do not roll back the canonical purchase transaction. They create a retryable synchronization state.

## Milestone 8 purchase projection

The committed PURCHASE_CREATED event is handed off atomically to one owned
WalletPass and acknowledged independently of inventory/insights. Existing purchase
events are backfilled in batches of twenty. The pass starts PENDING, is leased as
SYNCING, and ends SYNCED, RETRY or FAILED. Missing configuration fails visibly without
Google I/O. Three attempts, 5/10-second backoff and bounded Retry-After apply to
transient failures; permanent/exhausted jobs require explicit requeue. Expired
five-minute leases recover crashes and stale workers cannot finalize local state.

The user can ensure/read/requeue a pass through the authenticated Wallet API and
request a signed save link after synchronization. Provider calls use the canonical
purchase snapshot and stable IDs; uncertain outcomes repeat an idempotent upsert.
Signed links contain existing object references and no receipt files or payment
credentials. Neither provider responses nor user saving changes canonical data.
Insight/inventory pass projections remain optional future work. See ADR-011.
