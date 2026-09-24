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
