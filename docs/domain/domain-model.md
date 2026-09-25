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

### Conversation / Message / ToolExecution
- persistent assistant conversation and auditable tool calls

### Memory
- durable user preference/goal/habit/constraint/fact
- source and confidence metadata

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
