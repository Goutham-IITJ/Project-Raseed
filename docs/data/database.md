# Raseed V2 Database Architecture

Primary database: PostgreSQL.

## Tables

users, user_preferences, receipts, extraction_runs, merchants, purchases, payments, line_items, products, categories, inventory_items, inventory_lots, inventory_events, insights, conversations, messages, tool_executions, memories, wallet_passes, market_price_observations, outbox_events.

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
