# Workflow A — Receipt Ingestion

## Goal

Convert an uploaded receipt artifact into validated canonical purchase data and durable downstream events.

## High-level flow

User upload → Receipt API → private object storage → transaction (Receipt record
and upload outbox event) → async job → multimodal extraction → schema validation →
semantic/business validation → normalization → transaction (Purchase/LineItem/Payment
and corresponding outbox events) → downstream workers → Inventory/Wallet/Insights/Analytics.

Canonical database state and its corresponding outbox event must be written in
the same PostgreSQL transaction. Inventory workers likewise commit inventory
events, aggregate changes, and corresponding outbox events atomically. Object
storage and external calls are not part of a PostgreSQL transaction.

Milestone 2 establishes the receipt/purchase schema and services. Milestone 3
implements this ingestion/extraction flow using those foundations. Milestone 4
adds inventory processing. This end-to-end workflow is not a Milestone 1 deliverable.

## Important design decisions

- Upload requests should not block on the AI model.
- Receipt binaries live in object storage; PostgreSQL stores metadata and URI.
- Model output must use a versioned schema.
- Application validation must run even when the model returns schema-valid JSON.
- Important numeric fields must reconcile where possible.
- Low-confidence or conflicting extraction can enter `NEEDS_REVIEW`.
- Duplicate protection uses content hash plus idempotency semantics.

## Receipt processing states

UPLOADED → PROCESSING → EXTRACTED → VALIDATING → NORMALIZED → PROCESSED

Failure or unresolved ambiguity can lead to NEEDS_REVIEW or FAILED.

## Events

- RECEIPT_UPLOADED
- PURCHASE_CREATED
- INVENTORY_UPDATE_REQUESTED
- WALLET_SYNC_REQUESTED
- INSIGHT_EVALUATION_REQUESTED

## Security

Receipt files are private. Access is authorized by the backend and may use short-lived signed URLs. Receipt text/image content is untrusted input and cannot control model behavior.
