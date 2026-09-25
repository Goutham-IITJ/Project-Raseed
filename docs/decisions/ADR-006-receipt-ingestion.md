# ADR-006 — Receipt ingestion and extraction

## Status

Accepted implementation of the requested Milestone 3 scope, building on ADR-005.

## API and private artifacts

POST /api/v1/receipts adds multipart/form-data with one `file` (JPEG, PNG, PDF),
returning 202 and the existing data envelope. The JSON metadata/201 contract
remains supported. Binary uploads validate content, MIME, extension, and a
configurable 10 MiB limit; PDFs are limited to 20 unencrypted pages. SHA-256 is
computed by the server. Completed duplicate uploads return 409 per owner.

ObjectStorage has put/get/delete operations. Local and Google Cloud Storage
adapters return opaque private references; no file URL or file route is exposed.
Local storage lives outside the web assets under a service-owned directory.
GCS requires uniform bucket access and public access prevention. Neither API
startup nor deterministic tests requires Google credentials.

Upload reserves PENDING_UPLOAD metadata with a renewable-by-retry lease, stores
the binary outside a database transaction, then commits UPLOADED and
RECEIPT_UPLOADED together. A failed or expired upload reservation can be retried
with the same bytes. Stored objects use unique attempt keys. Failed finalization
leaves the artifact recoverable; unreferenced objects may require operator cleanup
after a process crash. Object storage is not a distributed PostgreSQL transaction.

## Durable local worker and ownership

The existing outbox gains a receipt foreign key, availability time, and an
exclusive purchase-or-receipt event constraint. No separate job entity or broker
is introduced. The local dispatcher polls pending RECEIPT_UPLOADED events and
delivers typed event IDs through a TaskQueue interface to ReceiptProcessor in a
separate process. Local delivery is acknowledged only after a terminal result;
transient failure leaves the durable event available for retry. PURCHASE_CREATED
stays pending for later consumers. Cloud Tasks/HTTP delivery can implement the
same interface later; its deployment and endpoint authentication are deferred.

A narrow internal worker repository derives ownership from the durable event
and database user, never from a public request or model output. Receipt leases
use random tokens, expirations, and row locks. An expired worker cannot commit
after a new worker has claimed its receipt. A crashed RUNNING ExtractionRun is
closed as FAILED before the next attempt. Duplicate execution cannot create
another purchase because of both token checks and the existing unique receipt FK.

## Extraction and validation

ReceiptExtractor isolates providers. The first adapter uses Gemini's REST
generateContent endpoint, inline original bytes, JSON-schema constrained output,
an environment-selected model, an explicit timeout, and no hidden retries.
The versioned prompt treats receipt content as untrusted data, forbids inferred
financial values and payment credentials, and requests decimal strings.

`receipt.v1` preserves nullable dates/times, amounts, payment details, invoice
number, language, notes, confidence, and provenance. Schema validation precedes
financial reconciliation and domain validation. Important missing facts, missing
or low confidence, inferred financial facts, and contradictory totals cause
NEEDS_REVIEW. Raw/normalized outputs and safe reason codes stay on ExtractionRun;
public views expose only safe processing reasons, attempt count, and purchase ID.

No missing numeric component becomes zero. A date without time remains unknown
and enters review because ADR-005 requires an exact canonical timestamp. An
observed local date/time may use the user's timezone setting when the receipt
omits a timezone; that conversion is recorded as DERIVED. Ambiguous/nonexistent
local times require review. Complete pre-tax/pre-discount item totals reconcile
exactly with subtotal when that basis is explicitly identified; other bases do
not imply multiplication or reconciliation rules.

Merchant identity uses deterministic Unicode normalization and exact address
matching, serialized during reuse/creation. Category suggestions match only
existing unambiguous categories; no taxonomy is invented. Products require an
observed, checksum-valid GTIN and adequate confidence; uncertain product metadata
stays in extraction provenance without forcing a Product association.

## Atomic success and recovery

The lifecycle follows PENDING_UPLOAD → UPLOADED → PROCESSING → EXTRACTED →
VALIDATING → NORMALIZED → PROCESSED. The final normalization, Purchase,
LineItems, Payments, PURCHASE_CREATED, ExtractionRun success, receipt success,
and local upload-event acknowledgement commit in one PostgreSQL transaction.
Rollback leaves no canonical aggregate or success event.

Transient storage, provider timeout/rate-limit/server, or persistence failures
produce FAILED attempts and bounded exponential retries (three by default).
Permanent failures and exhausted retries remain FAILED with retained artifacts.
Validation failures enter NEEDS_REVIEW without automatic retries. An operator
may explicitly retry a failed/review receipt through the worker CLI after fixing
the cause; prior ExtractionRuns remain auditable. No correction UI, inventory,
assistant, or downstream event consumer is added.
