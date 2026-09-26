# ADR-007 — Event-derived inventory

## Status

Accepted implementation clarification for the requested Milestone 4, within the
approved modular monolith, PostgreSQL, and outbox architecture.

## Eligibility and identity

No category taxonomy or reliable goods classifier was specified. Nullable
`inventory_eligible` catalog flags express explicit eligibility: product first,
then the line category (or product category) and its nearest configured ancestor.
False excludes a line; null means unknown. Automatic enrollment additionally
requires an observed positive quantity and nonblank unit. No name heuristics,
default quantity of one, unit conversion, or provider calls are introduced.
An owned purchase-candidates endpoint explains each decision. The user can
explicitly track an owned line with a quantity and unit, including unknown or
excluded lines; that confirmation is recorded as USER evidence, not a financial
purchase edit. One lot per line prevents duplicate acquisition effects.

Inventory items group lots only by canonical product and normalized unit within
one owner. Without a canonical product, identity stays specific to the line;
similar names do not prove identical products. Units use Unicode normalization,
whitespace collapse, and case folding, without converting between units.

## Ledger and ownership

The three blueprint tables are inventory_items, inventory_lots, inventory_events.
Items store identity, lots retain acquisition/purchase linkage, and immutable
events store quantity deltas, per-lot sequence, source, reason, actor, and optional
expiry evidence. Remaining and acquired quantities and current expiry are read
projections of events, not writable quantity columns. Database triggers prohibit
updating/deleting ledger entries. Deletion of referenced inventory is restricted.
Composite foreign keys enforce owner, item, purchase, line, and outbox consistency.

All mutations lock the owner row before reading inventory balances. This simple
initial serialization prevents overspending and cross-lot idempotency races.
User mutations require an expected lot version; stale writes return 409. A
CORRECTION specifies an absolute remaining quantity and/or replacement expiry;
the service records its delta against the locked event sum. Other supported
events are PURCHASED, CONSUMED, EXPIRED, DISCARDED, RETURNED, MANUAL_ADJUSTMENT.
Balances cannot become negative or exceed NUMERIC(20,6). User-supplied signed
adjustments require a reason; no broad or implicit destructive action exists.

## Expiry

Expiry changes are explicit event evidence. Unknown dates remain null with source
UNKNOWN and null confidence. Known dates require a source and confidence in [0,1].
RECEIPT/USER are OBSERVED, PRODUCT_KNOWLEDGE is EXTERNAL, MODEL_ESTIMATE is INFERRED.
Public corrections can assert only USER or clear to UNKNOWN. A typed internal
service contract accepts other evidence sources for future trusted adapters;
M3 receipt.v1 contains no expiry, so automatic acquisition starts UNKNOWN.
The latest expiry-bearing event defines current expiry. Due/past-due is computed
in the owner's timezone and explicitly separated from physical stock: passing a
date never silently consumes or discards stock, including estimated expiry.
Users explicitly record EXPIRED or DISCARDED quantities. No estimation provider
or automatic expiry sweep is part of this milestone.

## Delivery and transactions

A second typed task/queue boundary handles PURCHASE_CREATED in the existing local
worker process. No external calls occur during inventory processing. One database
transaction locks the event and owner, creates eligible items/lots/PURCHASED
events and INVENTORY_CHANGED outbox entries, and acknowledges PURCHASE_CREATED.
Ineligible purchases are acknowledged without stock effects. Already-enrolled
lines are skipped. A crash/rollback leaves the original event pending and no
partial inventory effect. Unique line-lot and lot-sequence constraints provide
additional protection. Public commands use a UUID idempotency key unique per
owner; a canonical request hash rejects changed input under the same key.

Purchase delivery failures persist bounded exponential retry state on the outbox
(three attempts, 5/10 second delays); exhausted jobs stay visibly failed and can
be requeued explicitly by purchase ID. Receipt delivery/lease logic is unchanged.
For this milestone, inventory is the sole PURCHASE_CREATED consumer; published_at
means its local acknowledgement, as for M3 receipt jobs. INVENTORY_CHANGED is
durable and pending for later features. Future multiple subscribers will require
an explicit fan-out/delivery contract; no later feature is silently implemented.

Each inventory mutation and its INVENTORY_CHANGED entry commit atomically.
Outbox entries link uniquely to the owned inventory event and carry only IDs.
No endpoint mutates canonical purchase quantities or exposes another owner's data.

## API

Version-one additions are documented in api-contract.md: inventory items, lots,
event history, explicit lot enrollment and event creation, and owned purchase
eligibility inspection. All retain the existing authentication, pagination,
decimal-string, response-envelope, and error contracts. No inventory UI or
assistant is required by this subsystem milestone.
