# Raseed V2 Domain Model

## Core entities

### User
- id (UUID)
- Firebase uid (unique); internal UUID remains the application identity
- email / display name
- currency / timezone / locale
- timestamps

### UserPreference
- user_id
- key/value
- timestamps

Milestone 1 supports only currency, timezone, and locale. Each user has three
preference rows, unique by `(user_id, key)`, initialized to INR, Asia/Kolkata,
and en-IN. These rows are canonical preferences; the matching User columns are
an effective-profile projection updated in the same transaction. Preferences are
explicit user settings, not inferred values. See ADR-004 for ownership and concurrency.

Budget persistence is a later design decision. No budget entity or preference
encoding is introduced in Milestone 1.

### Receipt
- id
- user_id
- storage URI
- original filename
- MIME type / size / content hash
- source
- status
- upload/process timestamps

Metadata-only records start as `PENDING_UPLOAD`; storage URI and upload/process
timestamps remain null until real ingestion. Content-hash uniqueness is scoped
to user ownership. See ADR-005 for the Milestone 2 field/constraint decisions.

### ExtractionRun
- id
- receipt_id
- provider / model
- prompt version / schema version
- status
- raw and normalized output
- error/provenance fields
- timestamps

### Merchant
- canonical and raw/normalized identity data
- optional location data

### Purchase
- id
- user_id
- receipt_id
- merchant_id
- purchase_type
- category_id
- purchase timestamp
- currency and exact monetary amounts
- payment status
- notes

### Payment
- purchase_id
- method
- exact amount / currency
- optional provider/reference/last4 metadata

### LineItem
- purchase_id
- product_id (nullable)
- category_id
- raw and normalized item names
- quantity/unit
- unit price / line total

### Product
- canonical name
- optional brand/category/unit type
- metadata

### Category
- hierarchical category tree via parent_id

No fixed taxonomy is currently approved; Milestone 2 seeds no category rows.

### InventoryItem
- user-level current aggregate view

### InventoryLot
- item/batch acquired from a specific line item
- quantity acquired/remaining
- acquisition date
- optional expiry with source/confidence

### InventoryEvent
- purchase, consumption, expiry, discard, return, manual correction, etc.
- quantity delta
- source/reason/actor

Milestone 4 implements these as an append-only ledger. Item identity groups only
confirmed product/unit pairs per owner; unassociated lines remain separate. Each
lot is unique to one owned purchase line. Acquired/remaining quantities and latest
expiry are derived from events, with no writable quantity field. Explicit catalog
eligibility drives automatic acquisition; unknowns can be confirmed by the user.
Corrections append events with version/idempotency guards. Expiry preserves date,
source/confidence and observed/external/inferred provenance. See ADR-007 and the
inventory workflow for eligibility, event types, transactions and API semantics.

### Insight
- user_id
- type/title/summary
- source and calculation data
- confidence/status
- time period and lifecycle

### WalletPass
- user/purchase linkage
- pass type/provider/class/object IDs
- synchronization state

M8 has one GOOGLE/GENERIC pass per owned canonical purchase. Stable external IDs,
per-cycle attempts, availability, safe last errors, last successful sync and leased
processing form a durable external-projection lifecycle. An owned composite FK
protects the purchase link. Google success records acceptance of canonical data,
not canonical financial evidence or proof that a user saved the pass. No provider
payload, signed link, private receipt URL or payment instrument is persisted here.
See [ADR-011](../decisions/ADR-011-google-wallet.md).

### Conversation / Message / ToolExecution
- persistent assistant conversation and auditable tool calls

Milestone 6 conversations are owned by one authenticated user. Messages reserve
ordered USER/ASSISTANT pairs with a per-conversation idempotency key and one reply
per user message. Assistant replies move from PROCESSING to COMPLETED or FAILED;
leases fence stale workers and only one turn can process per conversation.
Tool executions belong to the assistant reply and retain their name, call ID,
arguments, structured result/error, status, and timing. Composite ownership FKs
prevent linking messages or executions across owners/conversations. Model wording
is INFERRED; cited values resolve from canonical service results. See ADR-009.

### Memory
- durable user preference/goal/habit/constraint/fact
- source and confidence metadata

Milestone 7 stores explicit user-confirmed memories independently of messages.
Each has an owned UUID, typed content, optional relevance topics and expiry,
USER_EXPLICIT source, OBSERVED provenance, confidence 1 for the assertion,
optional owned USER-message source, version and timestamps. Version guards protect
corrections/deletion. Expired/deleted memories are excluded from future assistant
retrieval. Memory never replaces canonical user settings or financial records.

M7 insights retain typed canonical source snapshots, versioned calculation rules,
deterministic title/summary, DERIVED provenance, nullable confidence, expiry,
evaluation/update times, version and ACTIVE/READ/DISMISSED/RESOLVED/EXPIRED status.
User dismissal survives refresh of the same logical signal. The worker generates
spending-change, unusually large purchase and recorded-inventory-expiry observations.
See [ADR-010](../decisions/ADR-010-memory-insights.md).

### MarketPriceObservation
- normalized product/merchant/price/currency/location
- source and observation time

### OutboxEvent
- durable domain event waiting for asynchronous processing

## Key relationships

User → Receipts → ExtractionRuns
User → Purchases → Payments / LineItems
LineItems → Products / Categories
LineItems → InventoryLots → InventoryEvents
Purchases → WalletPasses
User → Conversations → Messages → ToolExecutions
User → Memories / Insights
Products → MarketPriceObservations
