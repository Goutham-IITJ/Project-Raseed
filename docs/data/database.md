# Raseed V2 Database Architecture

Primary database: PostgreSQL.

## Tables

users, user_preferences, receipts, extraction_runs, merchants, purchases, payments, line_items, products, categories, inventory_items, inventory_lots, inventory_events, insights, conversations, messages, tool_executions, memories, wallet_passes, market_searches, market_price_observations, outbox_events.

## Principles

- use UUIDs for application identifiers
- use exact numeric/decimal types for money
- use foreign keys and unique constraints aggressively
- use SQLAlchemy and Alembic migrations, not ad-hoc CREATE TABLE IF NOT EXISTS scripts
- use JSONB for bounded, genuinely variable metadata, not as a substitute for the relational model
- keep receipt binaries in object storage
- index common access paths by user_id and timestamps
- add uniqueness where idempotency requires it

## Transaction boundary

Canonical database state and its corresponding outbox event must be written in
the same PostgreSQL transaction. This includes canonical purchase creation.
Publishing happens after commit; never commit state and its corresponding event
separately. Milestone 1 has no defined domain events and does not add an outbox
table or dispatcher ahead of the later event-producing workflows.

Inventory state is changed through inventory events and service logic.

## Ownership

All user-owned rows are filtered/authorized by the authenticated server-side user context.

## Milestone 1 schema

Only `users` and `user_preferences` are introduced. Users have an internal UUID,
unique nonempty Firebase uid, nullable email/display name, currency/timezone/locale,
and timezone-aware creation/update timestamps. Email is not an identity key.
Preferences have a UUID, non-null user foreign key with cascade deletion, a
constrained key (currency/timezone/locale), a non-null string value, timestamps,
and uniqueness on `(user_id, key)`. Defaults and projection semantics are defined
in the domain model and ADR-004. No legacy database is imported or modified.

## Milestone 2 schema

Revision `0002_purchase_foundation` adds receipts, extraction_runs, merchants,
categories, products, purchases, line_items, payments, and the required durable
outbox foundation. See [ADR-005](../decisions/ADR-005-canonical-purchase-foundation.md)
for exact nullability, NUMERIC(20,6), duplicate rules, ownership foreign keys,
reference-data scope, and intentional deletion behavior. No catalog taxonomy is
seeded and no existing identity data is rewritten.

## Milestone 3 schema

Revision `0003_receipt_ingestion` adds receipt lease tokens/expiration, attempt
counts, and safe failure fields. Outbox events gain a receipt ownership foreign
key and availability timestamp. A check constraint requires exactly the correct
aggregate link for RECEIPT_UPLOADED or PURCHASE_CREATED; receipt/event uniqueness
and the existing purchase/receipt uniqueness enforce idempotency. No new tables
or canonical monetary changes are introduced. See ADR-006 for transaction and
recovery rules. Downgrading to M2 discards upload-delivery events and ingestion
state fields, while retaining canonical purchases and PURCHASE_CREATED events;
test downgrades run only on the disposable database.

## Milestone 4 schema

Revision `0004_inventory` adds inventory_items (owned identity), inventory_lots
(unique purchase-line acquisition), and inventory_events (append-only quantity
and expiry history). Deltas use NUMERIC(20,6), confidence NUMERIC(7,6). Quantities
are read aggregates. Owner serialization and ledger guards enforce consecutive
sequences and nonnegative bounded balances; event updates/deletions are rejected.

Composite FKs enforce lot→item owner, lot→purchase owner, lot→line purchase,
event→lot owner and outbox→event owner. Uniqueness covers line→lot, lot/sequence,
user/idempotency key and one INVENTORY_CHANGED per event. References are RESTRICT.
Indexes cover owner lists, item/purchase links, event order and expiry evidence.
Source/actor/expiry/sign checks reject inconsistent ledger rows.

Products/categories gain nullable inventory_eligible flags; migration classifies
no existing catalog records. Outbox gains an inventory-event FK, purchase-delivery
attempt_count/failure_code/failed_at and a ready-job index. The exclusive event
link check retains M3 kinds and adds INVENTORY_CHANGED.

Downgrade discards inventory history/flags and resets M4-handled PURCHASE_CREATED
events to pending for later reconstruction. Canonical receipts/purchases survive.
Round trips are tested only on the disposable database. See ADR-007.

## Milestone 5 indexes and reads

Revision `0005_financial_analytics` changes indexes only. Purchases gain composite
indexes on (user_id, currency, purchased_at, id), (user_id, merchant_id, purchased_at,
id), and (user_id, category_id, purchased_at, id). Existing owner/time ordering
remains supported. Line-item product/category indexes gain purchase_id as a second
column for filtered history EXISTS queries, retaining their leading-key access paths.

Analytics aggregates canonical NUMERIC amounts within each currency and never
casts to floating point or to a bounded per-record numeric type. Child payments
are aggregated before joining purchases. Direct range predicates use UTC instants
resolved from the owner's local dates. Read-only REPEATABLE READ transactions give
multi-query analytics consistent preferences and purchase snapshots; existing
write transactions retain READ COMMITTED. No materialized financial table, new
event consumer, or budget persistence is added. Index-only downgrade preserves
all canonical and inventory records. See ADR-008.

## Milestone 6 assistant persistence

Revision `0006_assistant_tools` adds the three blueprint entities only:

- conversations: owned UUID, nullable title, next message sequence, UTC timestamps.
- messages: owned conversation/sequence, role/status/content, submission key or
  unique reply link, model/prompt/schema provenance, attempt count, safe failure
  fields, processing lease, timestamps, and bounded JSONB answer evidence.
- tool_executions: owned assistant-message link, unique per-message provider call
  ID, tool name, raw/validated arguments, request hash, structured result/error,
  status, and start/end/elapsed timing.

Composite foreign keys enforce conversation and reply/execution ownership.
Checks enforce role-specific fields, terminal content/error/evidence, and lease
lifecycle. Unique keys enforce conversation sequence, submission idempotency,
one reply per user message, and one PROCESSING reply per conversation. Indexes
support owner/conversation message order and per-message tool history. JSONB holds
only bounded tool payloads and response evidence; relational ownership and state
remain normal columns. No provider reasoning or raw response is persisted.

Services reserve, audit, and finalize in short transactions. Provider calls and
backoff hold no database transaction or row lock. Domain tools retain their own
service transaction rules; repeated call IDs replay the persisted result. Upgrade
preserves M1–M5 data. Downgrade drops assistant history only. See ADR-009 for stale
lease recovery, limits, retry semantics, and evidence validation.

## Milestone 7 memory and insights

Revision `0007_memory_insights` adds `memories` and `insights`. Both use explicit
user foreign keys, UUIDs, UTC timestamps and version guards. Memory's optional
message/conversation/owner composite FK protects source attribution. Type, explicit
source/provenance/confidence, content, expiry and version checks enforce its domain.
A GIN simple-language full-text index supports relevance alongside owner/time/expiry
indexes. The searchable text is a derived projection of content and relevance topics.

Insights have unique owner/deduplication keys, constrained lifecycle/provenance and
confidence, bounded source/calculation JSONB, and owner/status/expiry, creation and
scope indexes. Canonical financial values in evidence serialize as exact strings.
Inventory source records preserve their lot version and expiry provenance.

Outbox gains insight and evaluation-lot ownership FKs, unique insight and per-owner
schedule keys, and independent insight delivery state: insight_processed_at,
insight_available_at, insight_attempt_count, insight_failure_code, insight_failed_at.
The existing published_at and retry fields retain their M3/M4 meaning. A partial
index selects ready insight jobs. The event-kind/link constraint additionally
allows INSIGHT_EVALUATION_REQUESTED and INSIGHT_CREATED; all events gain a direct
user FK. Existing domain events are marked evaluated only for the new subscriber;
daily scheduling evaluates current data without replaying every historical event.

Upgrade preserves M1–M6 tables and original delivery state. Downgrade removes only
M7 memories, insights, event kinds, links and subscriber fields. Tests compare
canonical/M6 rows and original outbox state across the round trip. See ADR-010.

## Milestone 8 Wallet persistence

Revision `0008_google_wallet` adds wallet_passes with UUID/owner/purchase,
provider/type, nullable stable class/object IDs, lifecycle, attempt/availability,
lease, safe last-error and sync/creation/update fields. Composite purchase/owner
FKs, purchase/provider/type uniqueness, provider/object uniqueness and lifecycle
checks protect ownership and retries. Indexes cover owned lists and ready jobs.

Outbox adds wallet_processed_at and a partial index for unhanded PURCHASE_CREATED
events. A short transaction inserts the pass job and marks this handoff together.
Old events remain eligible for bounded backfill; no original delivery state is
reset. No new domain event or queue table is introduced. External calls hold no
database transaction. Downgrade drops only M8 local state and leaves canonical
data and remote Google objects intact; reconstruction uses the same stable IDs.
See ADR-011 and the dedicated migration preservation test.

## Milestone 9 market intelligence

Revision `0009_market_intelligence` adds market_searches and
market_price_observations. Searches retain owner/target relations, bounded canonical
snapshot JSONB, destination/currency/fingerprint, lifecycle, attempts, leases,
safe failure codes and cache/completion timestamps. A partial unique active
owner/fingerprint index and owner serialization prevent duplicate concurrent jobs.

Observations retain relational price/source/provider/merchant/location/URL/times,
exact NUMERIC(20,6) costs and bounded variable identity/pack/availability evidence.
Matching status, NUMERIC(7,6) rule confidence, rule version and DERIVED provenance
are distinct from EXTERNAL offer provenance. Nullable shipping/tax are not zeros.
Composite search/owner, purchase/owner, line/purchase and outbox/search/owner FKs
protect attribution. Unique request/provider/offer keys prevent duplicate evidence.

The outbox gains only market_search_id, its ownership FK/unique key and support
for MARKET_SEARCH_REQUESTED. Existing delivery fields keep their prior meanings;
the new event is acknowledged through published_at. No M1–M8 events are reset or
replayed. Downgrade removes M9 requests/observations/events only, leaving canonical
data and Wallet/inventory/insight subscriber state intact. See ADR-012.
