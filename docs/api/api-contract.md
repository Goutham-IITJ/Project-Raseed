# Raseed API v1 — identity, purchases, and receipt ingestion

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
