# Raseed API v1 — identity, purchases, receipts, and inventory

## Transport, versioning, authentication

Endpoints live under `/api/v1`; responses use JSON and binary uploads use multipart.
Breaking contracts require a new API version
and ADR. Use HTTPS in production. CORS permits explicitly configured web origins.
Every endpoint below requires `Authorization: Bearer <Firebase ID token>`.
The Firebase Admin SDK verifies tokens; uid resolves to an internal UUID through
concurrency-safe first-request provisioning. No Raseed session cookie is issued.

Ownership comes exclusively from verified server context. Identity endpoints accept
no query parameters. Collection endpoints accept only documented pagination.
No endpoint accepts user ID, Firebase uid, or email as an ownership selector.
Unknown body fields and query parameters are rejected with 422. Unauthenticated
requests are rejected before provisioning or reading user data.

## Success responses

Reads and updates return HTTP 200; receipt metadata creation returns 201;
accepted binary uploads return 202.
Responses use `{"data": ...}`. UUIDs are strings and
timestamps are ISO 8601 UTC values. Responses use `Cache-Control: no-store`.

### GET /api/v1/me

Returns `data` with `id`, `firebase_uid`, nullable `email` and `display_name`,
`currency`, `timezone`, `locale`, `created_at`, and `updated_at`.

### GET /api/v1/me/preferences

```json
{"data":{"currency":"INR","timezone":"Asia/Kolkata","locale":"en-IN"}}
```

### PATCH /api/v1/me/preferences

Supply one or more of `currency`, `timezone`, `locale`. Omitted settings remain
unchanged. Null values, an empty object, unknown fields, and invalid values return
422. Currency is uppercase ISO 4217; timezone is an IANA name; locale is a
recognized language[-Script][-REGION] tag, normalized to hyphenated form.

```json
{"currency":"USD","timezone":"America/New_York","locale":"en-US"}
```

Returns the full preferences object in the same envelope as GET. Updates affect
only the authenticated user, with preference rows and user profile projection
committed atomically. Concurrent partial updates preserve unrelated fields.

## Errors

```json
{"error":{"code":"unauthorized","message":"A valid bearer token is required."}}
```

- 401 `unauthorized`: missing, malformed, expired, revoked, or otherwise invalid
  token; includes `WWW-Authenticate: Bearer`.
- 422 `validation_error`: invalid body, unsupported field/query, or setting value.
- 404 `not_found`: resource missing or owned by another user (same response).
- 409 `conflict`: duplicate receipt hash or other conflicting canonical identity.
- 413 `upload_too_large`: upload exceeds the configured byte limit.
- 415 `unsupported_receipt`: unsupported or invalid file content, MIME/extension
  mismatch, encrypted PDF, or excessive PDF page count.
- 503 `storage_unavailable`: private object storage could not accept the receipt.
- 503 `authentication_unavailable`: identity verification infrastructure unavailable.
- 503 `database_unavailable`: database operation unavailable.
- 500 `internal_error`: unexpected failure, without internal details or token contents.
- Other HTTP errors use this envelope (for example 404 `http_error`).

## Operational endpoint

`GET /health` is an unauthenticated liveness check returning `{"status":"ok"}`.
It does not provision users or imply database/Firebase readiness. API docs are
available at `/docs`. No other product API is implemented in Milestones 0–1.

## Receipt binary upload (Milestone 3)

### POST /api/v1/receipts — multipart/form-data

Send exactly one `file` part with an original filename and MIME type. Supported
extensions: .jpg/.jpeg (image/jpeg), .png (image/png), .pdf (application/pdf).
Content is inspected, not trusted from the header. Default maximum: 10 MiB;
PDFs must be unencrypted with 1–20 pages. Extra form fields/files or query
parameters are rejected. Authentication occurs before multipart parsing.

The backend computes SHA-256, reserves metadata, stores the private original,
then commits UPLOADED and its durable processing event. It returns 202 with
`{"data": {receipt fields}}` and `status: "UPLOADED"`. No model runs in the HTTP
request. Poll GET /receipts/{id} for processing completion. Duplicate stored
content for the same user returns 409, regardless of filename. Other users may
upload identical content independently. Failed/expired incomplete upload
reservations can be retried by posting the same bytes; the receipt ID is retained.

Receipt views retain the existing metadata fields and add:

- `purchase_id`: UUID or null; populated after canonical processing succeeds.
- `attempt_count`: attempts in the current processing retry cycle, initially zero.
- `failure_code`, `failure_message`: safe review/failure information or null.

`status` is the processing state; `uploaded_at` and `processed_at` distinguish
artifact acceptance and canonical completion. No internal storage URI, user ID,
lease, prompt, raw provider response, or credentials are returned. No private
file-download endpoint is currently needed or exposed.

NEEDS_REVIEW is terminal until explicit operator reprocessing; FAILED may be
scheduled for bounded automatic retry or need operator attention. This milestone
does not expose a public correction or retry endpoint. See the ingestion workflow.

## Compatible Milestone 2 receipt metadata and purchase reads

All endpoints below require the same Firebase authentication. `storage_uri`,
user IDs, extraction outputs, and payment credentials are never accepted by the
metadata API. A JSON metadata POST does not upload content or invoke an AI provider.

### POST /api/v1/receipts — application/json

```json
{
  "original_filename": "receipt.jpg",
  "mime_type": "image/jpeg",
  "file_size": 12000,
  "content_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "source": "USER_UPLOAD"
}
```

Required fields: a non-path filename (max 255 characters), MIME type
(`image/jpeg`, `image/png`, `image/webp`, or `application/pdf`), positive byte size,
lowercase SHA-256 hash, and a nonempty source label (max 40 characters).
Unknown fields are rejected. Metadata is a client claim, verified against actual
bytes only in Milestone 3. The created receipt has status PENDING_UPLOAD, null
uploaded_at/processed_at, and server creation/update timestamps. Its response
contains id and those metadata fields; internal storage_uri and user_id are omitted.
The same hash for the same user returns 409; another user's identical hash is allowed.

### GET /api/v1/receipts

Returns `{"data": [receipt, ...]}` for the authenticated user, newest creation
timestamp first with UUID as a stable tie-breaker. Optional `limit` (1–100, default
20) and `offset` (0–10000, default 0). No other query parameters are allowed.

### GET /api/v1/receipts/{id}

Returns metadata and the processing fields documented above. Invalid UUID: 422.
Missing or cross-user UUID: 404.

### GET /api/v1/purchases

Same pagination envelope and bounds; ordered by purchased_at and UUID descending.
Returns only the current user's purchases, including nested line_items and payments.

### GET /api/v1/purchases/{id}

Returns id, nullable receipt_id/merchant_id/category_id, merchant_name_raw,
purchase_type, purchased_at, currency, subtotal, discount_total, tax_total,
shipping_total, grand_total, payment_status, notes, timestamps, line_items, payments.
User ownership identifiers are omitted. Missing or cross-user UUID: 404.

Line items include id, nullable product_id/category_id, raw_name, normalized_name,
quantity, unit, unit_price, line_total, and timestamps. Payments include id, method,
amount, currency, nullable provider/reference/last4, and created_at. Exact numeric
fields are strings; unknown financial components remain null. Internal services
create purchases atomically; this milestone adds no purchase-write endpoint.

## Inventory (Milestone 4)

All endpoints retain Firebase authentication, data envelope, no-store responses,
404 for missing/cross-user IDs, and rejection of undocumented fields/parameters.
Quantities and confidence serialize as decimal strings. Clients cannot choose
ownership, event actor/source, or financial purchase fields.

| Method/path under /api/v1 | Response data |
| --- | --- |
| GET /inventory/items | Paginated item list |
| GET /inventory/items/{id} | One item |
| GET /inventory/items/{id}/lots | Paginated lots for the owned item |
| GET /inventory/lots | Paginated lot list |
| GET /inventory/lots/{id} | One lot with current state |
| POST /inventory/lots | Enroll one owned purchase line; 201 |
| GET /inventory/lots/{id}/events | Paginated history, newest sequence first |
| POST /inventory/lots/{id}/events | Record a user action; 201 |
| GET /purchases/{id}/inventory-candidates | Eligibility/existing lot per line |

Lists accept limit 1–100 (default 20), offset 0–10000 (default 0); items/lots sort
by created_at and UUID descending. Other routes accept no query parameters.
Depleted items/lots remain visible with zero balances and their history.

Item fields: id, name, nullable product_id, unit, quantity_remaining, lot_count,
created_at. Only confirmed product identity and identical normalized unit merge
lots; unidentified lines remain separate items.

Lot fields: id, item_id, purchase_id, line_item_id, name, unit, acquired_at,
quantity_acquired, quantity_remaining, version, expiry, created_at. Quantities and
version derive from history. Expiry has nullable date/confidence, source (RECEIPT,
USER, PRODUCT_KNOWLEDGE, MODEL_ESTIMATE, UNKNOWN), provenance (OBSERVED, EXTERNAL,
INFERRED, UNKNOWN), and status (UNKNOWN, NOT_DUE, DUE, PAST_DUE). Date status uses
the owner's timezone and never means stock was consumed.

Event fields: id, lot_id, sequence, event_type, quantity_delta, source (PURCHASE,
USER, SERVICE), actor (USER, INVENTORY_WORKER), reason, nullable expiry evidence,
created_at. Null expiry means unchanged; UNKNOWN clears prior evidence. History
omits time-dependent expiry status.

Candidate fields: line_item_id, nullable lot_id, eligible, reason,
eligibility_source (PRODUCT, CATEGORY, UNKNOWN), nullable quantity/unit, raw_name.
Reasons: ELIGIBLE, ALREADY_TRACKED, EXCLUDED, UNKNOWN_ELIGIBILITY,
MISSING_QUANTITY, MISSING_UNIT. Catalog precedence is in the inventory workflow.

### Enroll an owned purchase line

```json
{
  "idempotency_key": "de36b70c-16c5-4bde-837f-444bc4ea3b0f",
  "line_item_id": "987dfe77-bda0-4cdc-bdad-fb89169569a0",
  "quantity": "2",
  "unit": "each",
  "reason": "Confirmed these are in my pantry",
  "expiry": {"date": "2026-10-01", "source": "USER", "confidence": "1"}
}
```

Quantity must be positive, unit nonblank (max 40), reason nonblank (max 500).
Omitted expiry defaults to UNKNOWN. Explicit confirmation may enroll unknown or
excluded automatic candidates without editing purchases. One lot per line.

### Record consumption, expiry, discard, return, adjustment or correction

```json
{
  "idempotency_key": "c32f8d60-80fb-48ad-b5fb-744e239dff39",
  "expected_version": 1,
  "event_type": "CONSUMED",
  "quantity": "1",
  "reason": "Used one package"
}
```

Common required fields: idempotency_key, expected_version (positive integer),
event_type, reason. CONSUMED/EXPIRED/DISCARDED/RETURNED require positive quantity;
MANUAL_ADJUSTMENT requires nonzero signed quantity_delta; CORRECTION requires
nonnegative quantity_remaining and/or expiry. Unused fields must be omitted/null.
PURCHASED is created by enrollment/worker, not this route. A correction with
expiry {"source":"UNKNOWN"} clears the date. Public expiry permits only USER with
a valid full date/confidence [0,1], or UNKNOWN with null date/confidence. Other
sources are reserved for validated internal evidence.

Quantities accept exact decimal strings/integers, not floats, booleans, nonfinite
values; maximum magnitude is 99999999999999.999999 with six decimal places.
Stale version, insufficient stock, overflow, duplicate enrollment or changed
input under a reused idempotency key returns 409. Invalid shape returns 422.
No partial event/outbox survives a failed command. Identical retries return 201
with the previous event; enrollment retries return the same lot/current state.
Keys are unique across one owner's inventory commands.

No direct quantity PATCH or history deletion endpoint exists. Every correction
is retained and attributable. No live AI credentials are needed.
