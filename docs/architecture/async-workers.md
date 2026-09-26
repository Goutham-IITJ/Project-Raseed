# Raseed V2 Asynchronous Processing

## Why async

Receipt extraction, Wallet synchronization, market lookup, and scheduled insight generation can be slow or retryable. They should not block the user-facing request.

## Queue model

Initial strategy: durable application outbox + managed task queue/HTTP workers.

A database transaction writes both the canonical domain state and an outbox event. A dispatcher publishes tasks to workers. Google Cloud Tasks can deliver asynchronous HTTP tasks to worker endpoints such as Cloud Run. citeturn269522search9

## Worker types

- receipt-processing-worker
- wallet-sync-worker
- insight-worker
- memory-worker
- scheduled-analysis-worker
- market-observation-worker (on demand or scheduled)

## Retry policy

Retries should be bounded and classified:

- transient provider/network errors → retry with backoff
- rate limits → retry according to provider guidance
- semantic validation failures → no blind retry; route to review/reprocessing
- permanent authorization/configuration failures → dead-letter/failure state

## Idempotency

Workers must be safe to retry. Use stable job IDs / domain IDs and unique constraints so a retry does not create duplicate purchases, passes, or inventory events.

## Outbox rule

The outbox event is created in the same database transaction as the state change that caused it. Downstream processing can be eventually consistent without losing the originating event.

Canonical database state and its corresponding outbox event must be written in
the same PostgreSQL transaction. Milestones 0–1 provide only a worker package
skeleton; no queue, outbox dispatcher, or domain event is implemented yet.

## Milestone 3 implementation

`python -m backend.worker` is a separate durable outbox poller. OutboxDispatcher
delivers typed RECEIPT_UPLOADED event IDs through TaskQueue/LocalTaskQueue to
ReceiptProcessor. It never runs inside the upload request. Local delivery is
acknowledged in PostgreSQL on terminal processing; crashes leave pending events
and expiring receipt leases. Retryable failures use persisted exponential backoff.
The worker derives identity from the event and receipt, and final writes verify
the current lease token. Milestone 4 consumes PURCHASE_CREATED for inventory.

Cloud Tasks/HTTP deployment remains a later adapter for the same task contract;
there is no publicly exposed or unauthenticated worker endpoint. See ADR-006 and
the receipt-ingestion workflow for the implemented lease/retry rules.

## Milestone 4 implementation

The same worker process dispatches PurchaseTask through InventoryTaskQueue and
LocalInventoryTaskQueue. InventoryProcessor locks the purchase event and owner
and atomically commits lots, inventory events, INVENTORY_CHANGED entries and
local acknowledgement. It makes no provider calls. Inventory failure does not
roll back purchase success. Bounded retries/manual requeue use outbox delivery
fields; receipt leases are unchanged. Inventory is the sole purchase subscriber
in M4; INVENTORY_CHANGED remains pending. Later multiple subscribers require an
explicit fan-out contract. See ADR-007 and the inventory workflow.

## Milestone 7 implementation

InsightDispatcher/InsightTaskQueue/InsightProcessor join the same separate poller.
PURCHASE_CREATED now has independent inventory and insight acknowledgement/retry
state on its durable outbox row. INVENTORY_CHANGED has the insight subscriber;
the original published_at remains available for its future downstream contract.
INSIGHT_CREATED is recorded atomically with a new insight and has no M8 consumer.

The scheduler inserts uniquely keyed INSIGHT_EVALUATION_REQUESTED rows once per
owner/local date/timezone, plus owned lot jobs through a set-based insert. Scheduling
locks up to twenty due users with SKIP LOCKED; dispatch fetches at most twenty event
IDs. More work is drained by subsequent polling iterations. This is durable daily
evaluation, including clock-driven expiry, without API-side background tasks.

Insight delivery locks its event and owner, reads canonical service snapshots,
records observations and outgoing events, and acknowledges in one transaction.
No model call is needed. Independent failures cannot steal or reset inventory
acknowledgement. Retryable persistence failures get three attempts with five/ten
second backoff; invalid domain data fails permanently. Failure codes and explicit
operator requeue remain on the source outbox row. Duplicate delivery is a no-op.

Explicit memory CRUD is a short authenticated service transaction. No automatic
memory-extraction worker is introduced; saving every message is intentionally
excluded. See [ADR-010](../decisions/ADR-010-memory-insights.md).
