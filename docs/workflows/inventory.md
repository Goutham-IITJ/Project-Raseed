# Workflow C — Inventory

## Principle

Purchase history does not prove current physical inventory.

## Inventory flow

Purchase → InventoryLot → InventoryEvent history → Current InventoryItem state.

## Event types

- PURCHASED
- CONSUMED
- EXPIRED
- DISCARDED
- RETURNED
- MANUAL_ADJUSTMENT
- CORRECTION

## Expiry semantics

Every expiry estimate stores:
- date
- source
- confidence

Sources include RECEIPT, USER, PRODUCT_KNOWLEDGE, MODEL_ESTIMATE, UNKNOWN.

Never present an inferred expiry as an observed fact.

## User corrections

User actions create explicit inventory events. Do not silently overwrite inventory quantity.

Examples:
- “I finished the shampoo.” → CONSUMED event.
- “I still have one.” → USER correction event.

## Milestone 4 implementation

The PostgreSQL inventory module implements this workflow without model calls.
[ADR-007](../decisions/ADR-007-inventory.md) records concrete eligibility,
identity, transaction, expiry and API decisions left open by the blueprint.

1. Canonical purchase success commits PURCHASE_CREATED in the existing outbox.
2. The separate worker delivers a typed PurchaseTask through InventoryTaskQueue
   (LocalInventoryTaskQueue in development) to InventoryProcessor.
3. Eligibility uses explicit nullable catalog flags: product override, then line
   category or product category and its nearest configured ancestor. True means
   eligible; false means excluded; null means unknown. Positive quantity and a
   known unit are also required. No taxonomy is seeded and names are not guessed.
4. One transaction locks the event and owner, creates eligible items/lots,
   appends PURCHASED events, adds INVENTORY_CHANGED for each inventory event, and
   acknowledges PURCHASE_CREATED. Ineligible lines remain available as candidates.
5. Reads derive balances from SUM(quantity_delta), acquisition quantity from
   PURCHASED, version from sequence, and expiry from the latest expiry-bearing
   event. Item quantities sum associated lots; there are no mutable quantity caches.

Items group only the same canonical product and normalized unit within an owner.
Unidentified products stay separate per line. Units are Unicode-normalized and
case-folded without conversion. Lots reference one owned line and its purchase;
acquired_at copies the purchase timestamp. PostgreSQL rejects ledger edits and
invalid sequence/balances outside [0, 99999999999999.999999].

## User actions

GET /purchases/{id}/inventory-candidates explains ELIGIBLE, EXCLUDED,
UNKNOWN_ELIGIBILITY, MISSING_QUANTITY, MISSING_UNIT, or ALREADY_TRACKED per line.
POST /inventory/lots explicitly enrolls an owned line with quantity, unit and
reason, recording PURCHASED with USER source/actor. This may override unknown or
excluded eligibility, without editing financial history. One lot per line.

POST /inventory/lots/{id}/events records one explicit action:

- CONSUMED, EXPIRED, DISCARDED, RETURNED: subtract positive quantity.
- MANUAL_ADJUSTMENT: apply nonzero signed delta and reason.
- CORRECTION: set absolute remaining quantity and/or replace expiry. The service
  appends its calculated delta against the locked history; prior evidence survives.

Commands require UUID idempotency_key; lot changes require expected_version.
Stale versions, negative/overflowing results and changed input under a reused key
return 409 without writes. Identical retries return the previous event, or the same
enrollment lot with its current state. Keys span one owner's inventory commands.
Ownership derives from authentication; cross-owner reads/writes return 404.

## Expiry and current physical state

Expiry is {date, source, confidence}. UNKNOWN requires null date/confidence.
Known dates require confidence in [0,1] and source. RECEIPT/USER are OBSERVED,
PRODUCT_KNOWLEDGE is EXTERNAL, MODEL_ESTIMATE is INFERRED. Public commands can
assert only USER or clear to UNKNOWN. A typed internal service accepts validated
other evidence sources, with no provider SDK in inventory.

M3 receipt.v1 contains no expiry. Automatic acquisition therefore starts UNKNOWN.
No shelf-life heuristic invents dates. Partial/ambiguous evidence stays unknown;
event reasons can preserve its context. Lot views separately report UNKNOWN,
NOT_DUE, DUE or PAST_DUE using the owner's current local date. Date passage never
depletes stock, including estimated expiry. Users explicitly record EXPIRED or
DISCARDED quantities. No expiry scheduler or notifications are introduced.

## Transactions and recovery

Each user action and its INVENTORY_CHANGED entry commit atomically. Mutations
serialize on the owner row; sequence, line-lot and idempotency constraints add
duplicate protection. Failed validation/persistence leaves no partial stock event.
Duplicate jobs skip acknowledged events; already enrolled lines are skipped.
Crash/rollback retains the pending purchase event and no partial inventory effect.

Database failures use three bounded attempts with 5/10-second backoff. Domain
errors are terminal. Outbox attempt_count/failure_code/failed_at record failures;
exhausted jobs remain unpublished but leave polling. An operator can requeue
after fixing the cause with --retry-inventory <purchase-id>.

Inventory is the sole PURCHASE_CREATED consumer in M4. INVENTORY_CHANGED remains
pending for future features. Receipt success is independent of inventory failure;
M3 extraction and leases are unchanged. No later milestone is implemented.
See DEVELOPMENT.md for the deterministic local end-to-end check.
