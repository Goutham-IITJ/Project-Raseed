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

Milestone 3 implements uploads and extraction through canonical purchase success.
Milestone 4 adds inventory processing; all downstream feature consumers remain
deferred. ADR-006 specifies the implemented storage, task, and validation contract.

## Important design decisions

- Upload requests should not block on the AI model.
- Receipt binaries live in object storage; PostgreSQL stores metadata and URI.
- Model output must use a versioned schema.
- Application validation must run even when the model returns schema-valid JSON.
- Important numeric fields must reconcile where possible.
- Low-confidence or conflicting extraction can enter `NEEDS_REVIEW`.
- Duplicate protection uses content hash plus idempotency semantics.

## Receipt processing states

PENDING_UPLOAD → UPLOADED → PROCESSING → EXTRACTED → VALIDATING → NORMALIZED → PROCESSED

The compatible JSON metadata API creates PENDING_UPLOAD only. Multipart uploads
verify and store the original, then commit UPLOADED and RECEIPT_UPLOADED. The
separate worker processes that event. Canonical success commits PURCHASE_CREATED
to the outbox; Milestone 4 consumes it for inventory.

Failure or unresolved ambiguity can lead to NEEDS_REVIEW or FAILED.

## Events

- RECEIPT_UPLOADED
- PURCHASE_CREATED
- INVENTORY_UPDATE_REQUESTED
- WALLET_SYNC_REQUESTED
- INSIGHT_EVALUATION_REQUESTED

## Security

Receipt files are private. Access is authorized by the backend and may use short-lived signed URLs. Receipt text/image content is untrusted input and cannot control model behavior.

## Milestone 3 upload and storage

POST /api/v1/receipts accepts one multipart `file` and returns 202 with metadata
and status. It never calls a model or starts an in-memory background extraction
task. Authentication precedes parsing, request streaming is bounded, and the
server computes SHA-256. Default limit: 10 MiB; JPEG/PNG content must match MIME
and extension; PDFs must be parseable, unencrypted, and at most 20 pages.

ObjectStorage exposes put_object/get_object/delete_object. LocalStorageProvider
uses opaque `local://` keys under a service-owned directory, with no static-file
mount. CloudStorageProvider uses opaque `gs://` references, ADC, uniform bucket
access and enforced public access prevention. Credentials are unnecessary for
local storage and automated tests. No public or permanent file URL is exposed.

Metadata reservation and final upload commit are separate transactions around
storage I/O. Reservations have a token and five-minute lease. Failed storage
leaves a retryable FAILED record; an expired PENDING_UPLOAD reservation can be
reclaimed by uploading identical bytes. Finalization checks its token. Completed
duplicates return 409 per owner. Other owners may upload identical content.

An uncertain final database commit retains the uniquely keyed object rather
than risking deletion of a referenced artifact. Crashes may leave unreferenced
objects for operator cleanup; an automatic orphan sweeper is not included.

## Extraction schema and provenance

Schema: `receipt.v1`; prompt: `receipt-extraction.v1`. The typed schema lives in
`backend/app/ingestion/schema.py`. ReceiptExtractor isolates provider I/O.
GeminiReceiptExtractor uses generateContent, original inline bytes (including
the full PDF), responseJsonSchema, an environment-selected model, an explicit
timeout and no hidden retries. The versioned system prompt treats documents as
untrusted data and prohibits following document instructions.

The schema includes merchant/name/address, observed date and optional time/zone,
purchase type, currency, exact total components, payment evidence, invoice number,
line items, category suggestions, optional product evidence, language, notes,
confidence and financial provenance. Unknown values stay null. Money and
quantities are decimal strings. Invoice number, language, notes, uncertain product
metadata and model suggestions remain in ExtractionRun provenance.

Each claimed job creates a RUNNING ExtractionRun with provider, model, prompt
and schema versions and start time. EXTRACTED stores raw provider text; VALIDATING
stores typed extraction evidence. NORMALIZED and PROCESSED occur inside the
final canonical transaction, so polling may not observe NORMALIZED separately.
Schema/financial/business failures produce NEEDS_REVIEW and a FAILED run with a
safe reason. Operational failures produce FAILED. All prior runs and artifacts
remain available; no invalid extraction creates a trusted Purchase.

## Validation layers

1. Typed schema rejects malformed JSON, unsupported versions, extra fields,
   invalid dates/time/currency, binary-float money, negative or overflowing
   amounts, and nonpositive supplied quantities/payments. NUMERIC(20,6) is retained.
2. Financial checks reconcile complete subtotal/discount/tax/shipping components
   with grand total exactly. Complete line totals must match subtotal when the
   extraction explicitly identifies the SUBTOTAL basis. Do not assume unit-price
   multiplication or silently round discrepancies. Reliable supplied payments
   must match currency, total bounds and declared payment status.
3. Business checks require merchant, purchase type, currency, grand total and
   observed purchase date/time, financial_source OBSERVED, and confidence >= 0.85.
   Missing time enters review because canonical M2 purchases require a timestamp;
   midnight is never invented. Missing timezone may use the authenticated user's
   setting, recorded as DERIVED and USER_PREFERENCE. Ambiguous/nonexistent DST
   times and conflicting zones require review.

## Normalization

Merchant normalization uses Unicode NFKC, whitespace collapse and case-folding;
reuse requires unambiguous normalized name and matching address. Transactional
advisory locks serialize matching/creation without making names globally unique.
Raw merchant/item names remain on owned records. Item name normalization is
deterministic; model-suggested names remain separate extraction evidence.

Category suggestions match only existing unambiguous slugs/names. There is no
approved seeded taxonomy, so unknown suggestions stay unassigned. Products
require an observed, checksum-valid GTIN, name and confidence >= 0.9; otherwise
product_id stays null. Matching GTINs reuse existing products. Payment rows require
method, exact amount, currency and confidence >= 0.85; incomplete/uncertain payment
evidence is retained without creating an instrument. No missing amount becomes zero.

## Transactions, jobs and recovery

OutboxDispatcher runs in a separate process and delivers typed ReceiptTask event
IDs through TaskQueue/LocalTaskQueue. PostgreSQL is the durable pending-job store;
no additional broker or job table is introduced. WorkerRepository derives the
owner from the stored event/receipt; neither a client nor model chooses ownership.

The final transaction includes catalog normalization, Purchase, LineItems,
Payments, PURCHASE_CREATED, Receipt.PROCESSED, ExtractionRun.SUCCEEDED and local
upload-event acknowledgement. Rollback removes all of those canonical writes.
Milestone 4 consumes PURCHASE_CREATED and emits INVENTORY_CHANGED. Further feature
consumers remain deferred; inventory failure never reverses canonical success.

Uniqueness on (user, content hash), receipt-linked purchase, and receipt/event
protects duplicates. Workers acquire random lease tokens with expirations and
verify them before every write. Reclaiming an expired lease closes the previous
RUNNING run as FAILED; a stale model response cannot overwrite a newer result.

Transient storage/provider/network/database failures use persisted exponential
backoff (5s, 10s by default), with at most three attempts. Rate limits, timeouts
and provider 5xx are retryable. Configuration/auth failures and review results do
not receive blind retries. Exhausted receipts stay FAILED. An operator can use
`python -m backend.worker --retry <receipt-id> --once` after fixing the cause.
This starts a new attempt-count cycle while retaining prior runs. Successful
receipts cannot be retried into a second purchase.

Run API and `python -m backend.worker` separately. `--once` dispatches one ready
batch; future retries need another invocation or the polling loop. See DEVELOPMENT.md
for deterministic smoke checks and explicit live-provider verification.

GCS is implemented, but live GCS/Gemini checks require user credentials. Cloud
Tasks/HTTP delivery and service authentication are not deployed in this milestone;
a later adapter can deliver the same typed task. No public file route, correction
UI or later feature is implemented by M3. M4 inventory processing is documented
separately in [the inventory workflow](inventory.md).
