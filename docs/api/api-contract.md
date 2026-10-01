# Raseed API v1 — identity, purchases, receipts, inventory, analytics, assistant and Wallet

## Transport, versioning, authentication

Endpoints live under `/api/v1`; responses use JSON and binary uploads use multipart.
Breaking contracts require a new API version
and ADR. Use HTTPS in production. CORS permits explicitly configured web origins.
Every endpoint below requires `Authorization: Bearer <Firebase ID token>`.
The Firebase Admin SDK verifies tokens; uid resolves to an internal UUID through
concurrency-safe first-request provisioning. No Raseed session cookie is issued.

The explicit [local demo](../implementation/local-demo.md) is a development-only
exception using one fixed fixture credential and the same owned API contracts.
It cannot be selected in production configuration. It has no authentication
endpoint and does not accept a client-selected user. External provider actions
return `409 demo_external_action` in that mode.

Ownership comes exclusively from verified server context. Identity endpoints accept
no query parameters. Collection endpoints accept only documented filters and pagination.
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
storage reference or public download URL is exposed. M10 adds the owned original
file endpoint below.

### GET /api/v1/receipts/{id}/file (M10)

Returns the uploaded original bytes with the recorded MIME type,
`Content-Disposition: attachment`, `Cache-Control: no-store` and
`X-Content-Type-Options: nosniff`. Ownership is checked before storage access;
missing, foreign and not-yet-uploaded receipts return the same 404. Storage reads
take place outside the database transaction and verify the recorded content hash.
The browser displays a transient blob URL and revokes it when the viewer closes.

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
Milestone 5 adds the typed purchase-history filters documented below. Omitting
filters retains the existing all-time behavior, ordering, and response shape.

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

## Financial analytics and purchase history (Milestone 5)

All reads retain verified Firebase ownership, `{"data": ...}`, no-store responses,
and rejection of unknown query parameters. No query accepts an owner identifier,
SQL, arbitrary expression, or model-generated calculation. ADR-008 records the
financial semantics and snapshot policy. There are no analytics write routes.

| GET path under /api/v1 | Response data |
| --- | --- |
| /analytics/spending-summary | Period, filters, and summary per currency |
| /analytics/spending-by-category | Period, filters, basis, and category groups |
| /analytics/spending-by-merchant | Period, filters, and merchant groups |
| /analytics/period-comparison | Current/comparison periods and changes per currency |
| /analytics/spending-trend | Calendar buckets of spending per currency (M10) |
| /analytics/spending-by-payment | Recorded payment amounts and shares by method/currency (M10) |
| /purchases | Existing purchase list, with optional history filters |

### Shared period and purchase filters

- `start_date`, `end_date`: strict YYYY-MM-DD, supplied together, start < end.
  The start is inclusive and the end exclusive in the owner's current timezone.
- `period`: one of today, yesterday, this_week, last_week, this_month, last_month,
  this_year, last_year. Mutually exclusive with explicit dates. Weeks start Monday.
  A named period covers the whole local calendar period, including the remainder
  of a current week/month/year. Analytics defaults to this_month. Purchase history
  remains all-time if neither a period nor explicit dates are supplied.
- `currency`: optional uppercase registered currency code. Omitted means all
  currencies separately; the user's preferred currency does not hide other data.
- `merchant_id`: canonical merchant UUID.
- `category_id`: direct **purchase** category UUID; no descendant expansion.
- `line_item_category_id`, `product_id`: canonical UUIDs. A qualifying purchase
  must contain a matching line; when both are supplied they must match the same
  line. History returns each matching purchase once, with all its children.
- `purchase_type`: exact canonical label, nonblank, max 40 characters.
- `payment_status`: UNKNOWN, UNPAID, PARTIALLY_PAID, or PAID.

Filters combine with AND. Catalog IDs without qualifying owned purchases produce
empty results, identically for missing IDs and IDs used only by another owner.
No timezone override or user selector is supported. M10 adds `query` only to
purchase history: 1–200 nonblank characters, matched as a literal case-insensitive
substring of the recorded merchant name or any raw line-item name. SQL wildcards
are escaped. This combines with the filters and pagination above. Analytics
rejects `query`; clients must not recalculate spending from paginated search results.

Analytics data includes `provenance: "DERIVED"`, the validated `filters` object
(omitted filters are null), and `period` with start_date, end_date, timezone,
start_at and end_at. UTC boundaries are ISO 8601 timestamps. DST days may span
23/25 hours; ambiguous midnight uses its earliest occurrence. Nonexistent midnight,
skipped-date, or unrepresentable UTC boundaries return 422. Results use purchased_at,
independently of record creation time or database session timezone.

```text
GET /api/v1/analytics/spending-summary?start_date=2026-09-01&end_date=2026-10-01
GET /api/v1/analytics/spending-by-category?period=last_month&currency=INR&basis=line_item
GET /api/v1/purchases?period=last_month&currency=INR&payment_status=PAID&limit=20
```

### Summary and financial metrics

`currencies` is sorted by currency code. Each row contains currency, purchase_count,
total_spent, average_purchase, smallest_purchase, largest_purchase, first_purchased_at,
last_purchased_at, payment_count, recorded_payment_total, and
purchases_with_recorded_payments. Spending sums canonical Purchase.grand_total,
regardless of payment status; it does not measure cash flow. Recorded payments sum
Payment.amount for those purchases, independently of the payment's creation time.
An absent instrument does not establish an unpaid balance, even for PAID purchases.

Monetary values and percentages are decimal strings. Sums and differences are
exact at canonical six-place precision, without the per-record NUMERIC(20,6) cap
on aggregates. Averages and percentages round once to six places with HALF_EVEN.
No currency conversion is performed. Without a currency filter an empty selection
returns `currencies: []`; with one it returns that currency with zero totals/counts
and null average, extrema, and first/last timestamps.

### Category and merchant groups

Both endpoints accept limit 1–100 (default 20), offset 0–10000 (default 0).
They return `groups`, `limit`, `offset`, and `has_more`. Groups sort by currency
ascending, amount descending (unknown amounts last), and canonical UUID ascending
(null UUID last). Shares use the full filtered currency total before pagination.
The summary and comparison endpoints do not accept pagination.

Category `basis` is `purchase` (default) or `line_item`. Each group contains currency,
category_id/name/slug, parent_id, total_amount, purchase_count, line_item_count,
known_amount_count, unknown_amount_count, and share_of_known_total_percent.

- Purchase basis groups grand_total by the direct Purchase.category_id. Line count
  is null; known amount count equals purchase count. These totals reconcile with
  the summary over all pages.
- Line-item basis groups recorded line_total by direct LineItem.category_id.
  Missing values contribute to unknown_amount_count; total_amount is null when
  no amount is known. Purchase counts are distinct per group and can overlap
  across groups. Line filters also restrict which lines contribute. Other filters
  select the containing purchases. Product categories, quantity multiplication,
  discounts and taxes are never used to invent or allocate missing amounts.

Null category IDs form an unassigned group; no implicit parent roll-up occurs.
Line totals need not equal purchase totals. Shares are null for unknown totals
or zero denominators, and otherwise describe the known amounts only.

Merchant groups contain currency, merchant_id, merchant_name, total_spent,
purchase_count, average_purchase, first_purchased_at, last_purchased_at, and
share_of_total_percent. Canonical UUIDs define identity even when names match;
unassociated purchases form one null-ID/null-name group. No raw-name guessing occurs.

### Period comparisons

`comparison_start_date` and `comparison_end_date` optionally define a second
half-open local date range; supply both with start < end. Otherwise the comparison
is the preceding calendar day/week/month/year for named periods, or the preceding
equal number of local calendar days for an explicit current range. September
compares to August for `period=this_month`; an explicit 30-day range compares to
the preceding 30 local dates. Different-length explicit ranges are allowed, with
no per-day normalization. `comparison_period` returns the resolved boundaries.

`currencies` contains the union of currencies in either range, sorted by code.
Each row has currency, current_total, comparison_total, absolute_change,
percentage_change, current_purchase_count, comparison_purchase_count, and
purchase_count_change. Missing sides have zero totals/counts. Absolute change is
current minus comparison. Percentage change is delta / comparison * 100, or null
when the comparison total is zero (including zero-to-zero). The two ranges and
preferences are read from one consistent PostgreSQL snapshot.

Budget persistence, recurrence inference, and later insight features remain
deferred. These analytics endpoints perform no provider calls.

### Product analytics visualizations (M10 redesign)

`GET /api/v1/analytics/spending-trend` and
`GET /api/v1/analytics/spending-by-payment` accept the same typed period and
purchase filters as spending-summary, without pagination. Both return the normal
`data` envelope with `provenance: DERIVED`, `period`, and `filters`.

Trend adds `interval` (`day` through 62 days, otherwise `month`) and `points`:
`{date, currency, total_spent, purchase_count}`. Amounts are decimal strings.
Calendar buckets use the user's timezone and zero-fill gaps per currency.
An unfiltered empty period has no points; an explicit currency has zero-valued points
for every bucket. Ranges over 3660 days return 422. Monthly bucket dates identify
the first of the month, including a partial first/last month.

Payment distribution adds `groups`:
`{currency, method, total_amount, payment_count, share_of_total_percent}`.
Amounts and non-null percentages are decimal strings. These are recorded payment
amounts selected by the linked purchase date, not total spending or cash flow.
No absent payment is inferred. Groups sort by currency, descending amount, method.
Ownership, exact arithmetic, null ratios and snapshots follow ADR-008/ADR-013.

## Assistant (Milestone 6)

These routes use the same authentication, ownership, validation, error envelope,
and no-store headers. The model cannot select an owner, provider, role, SQL query,
or arbitrary tool. Tools are internal to orchestration; there is no public tool
execution endpoint. See [ADR-009](../decisions/ADR-009-assistant-tools.md).

### POST /api/v1/assistant/conversations

Body: `{}` or `{"title":"September purchases"}`. Title is nullable, nonblank when
present, and at most 200 characters. Unknown fields/query parameters are rejected.
Returns 201 with `{"data":{"id": "...", "title": "...", "created_at": "...",
"updated_at": "..."}}`. Timestamps are UTC. No model is called.

### GET /api/v1/assistant/conversations (M10)

Lists only the current user's conversations, ordered by updated_at and UUID
descending. Accepts the existing limit (1–100) and offset (0–10000) pagination;
unknown parameters are rejected. This read invokes no model.

### GET /api/v1/assistant/conversations/{id}

Returns the same conversation view with 200. No query parameters are accepted.
Missing and foreign conversations return the same 404 `not_found` response.

### POST /api/v1/assistant/conversations/{id}/messages

```json
{"content":"What did I spend last month?","idempotency_key":"a4a5c5c3-12e9-49e3-aab3-a1f7c4d71c71"}
```

Both fields are required. Content is nonblank text, at most 8000 characters, without
NUL. The UUID key identifies one submission within this conversation. Exact content
is retained and compared on replay; the backend does not normalize message text.
Unknown fields/query parameters are rejected. The server reserves a user message
and its assistant reply, performs a bounded synchronous assistant turn, and saves
the result before returning.

A new completed turn returns 201:

```json
{"data":{"user_message":{},"assistant_message":{},"replayed":false}}
```

The objects are the full message views below. An identical completed replay returns
200 with the original messages and `replayed:true`, without new model/tool calls.
An identical request still processing returns 202 with the existing PROCESSING
reply. A changed body under the same key or another new message while this
conversation is processing returns 409 `conflict`. Separate conversations can
proceed independently.

A failed turn returns the standard safe error envelope and remains available in
message history. Replaying its key returns the same failure without execution.
Retry with a new key to create a new turn. Processing leases expire after the turn
limit plus thirty seconds; a subsequent POST marks an expired reply and any running
tools failed before handling the request. GET never restarts or changes a turn.

Assistant failures:

| Status | Code | Meaning |
| --- | --- | --- |
| 503 | provider_configuration | Assistant key/model configuration unavailable |
| 503 | model_unavailable | Provider failed or exhausted transient retries |
| 503 | assistant_unavailable | Internal execution unavailable; safe failure persisted when possible |
| 504 | model_timeout | Provider request timed out after bounded retries |
| 504 | assistant_timeout | Total turn time limit reached |
| 504 | request_expired | Interrupted turn's lease expired; a new key is needed |
| 502 | model_invalid_output | Malformed, incomplete, or ungrounded model output |
| 502 | model_refused | Provider declined to return an answer |
| 502 | assistant_limit | Model/tool/context execution limit reached |
| 502 | tool_call_conflict | Same provider call ID reused with a different tool/payload |

Tool failures normally become structured feedback to the model. The assistant may
explain unavailable data or correct the query. They do not become fictitious
successful results or necessarily fail the whole turn. Database outages retain the
existing 503 `database_unavailable` behavior; an unfinishable reply remains subject
to lease recovery.

### GET /api/v1/assistant/conversations/{id}/messages

Returns `{"data":[message,...]}`, ordered by stable, increasing conversation
sequence. Only `limit` (1–100, default 20) and `offset` (0–10000, default 0) are
accepted. An owned empty conversation returns an empty array. Missing/foreign
conversations return 404. User and assistant messages each occupy one page row.

Message fields:

- `id`, `conversation_id`, `sequence`, `role` (USER/ASSISTANT), and `status`
  (PROCESSING/COMPLETED/FAILED).
- `content`: original user text or the rendered assistant reply; null while an
  assistant is processing or failed. `reply_to_id` is the user message UUID for
  assistant replies; `idempotency_key` appears only on the submitted user message.
- `provenance`: OBSERVED user input or INFERRED assistant prose.
- `evidence`: null except for completed assistant replies. Contains `kind`
  (answer/clarification/unavailable), `source_call_ids`, and `citations`. Each
  citation records its placeholder name, call ID, tool execution UUID, tool name,
  JSON pointer and exact scalar value. Monetary values remain decimal strings;
  unknown values remain null and render as “unknown”. Sources refer to persisted
  tool executions associated with this reply, never another turn.
- `provider`, `model`, `prompt_version`, `schema_version`, and `model_attempts`
  record orchestration provenance; nullable metadata and zero attempts on USER.
- `failure_code`/`failure_message` are safe, non-null only on FAILED replies.
- `created_at`, nullable `completed_at`, and `tool_executions`.

Tool execution views include `id`, `message_id`, `call_id`, `tool_name`, bounded
`raw_arguments`, nullable validated `arguments`, `status` (RUNNING/SUCCEEDED/FAILED),
nullable `result`, `started_at`, nullable `completed_at`, and nullable `elapsed_ms`.
Terminal results have `{"status":"SUCCEEDED","data":...,"error":null}` or
`{"status":"FAILED","data":null,"error":{"code":"...","message":"..."}}`.
No lease tokens, ownership IDs, database details, raw provider responses, or
reasoning content are exposed.

The eleven approved tools delegate to the implemented analytics, purchase, and
inventory services. Financial tools preserve the analytics response shapes under
result.data. Purchase tools wrap the canonical view under `purchase`, with OBSERVED
provenance and without payment provider/reference/last4 metadata. History and
inventory collections return `items`, `limit`, `offset`, and provenance; they are
pages, not unbounded totals. Inventory detail retains its existing typed view and
expiry evidence. Empty collections and null unknowns preserve their service meaning.
No tool result is silently truncated when it exceeds the 64 KiB result limit.

Assistant content is plain text. Clients must escape it or use a safe Markdown
renderer. Cited values are resolved by application code from recorded tool results;
explanatory prose remains inferred and does not become canonical financial state.

## Long-term memory (Milestone 7)

Memory is explicit user-confirmed information, separate from conversation history.
All routes authenticate and scope ownership on the server, reject extra fields,
and return no-store responses. Missing and foreign IDs both return 404. See
[ADR-010](../decisions/ADR-010-memory-insights.md) for retrieval and provenance.

### POST /api/v1/memories

```json
{"type":"PREFERENCE","content":"I am vegetarian","topics":["food"],"expires_at":null,"source_message_id":null}
```

`type` and `content` are required. Types: PREFERENCE, GOAL, HABIT, CONSTRAINT, FACT.
Content is nonblank PostgreSQL-safe UTF-8 text, at most 1000 characters. Optional
topics are a unique list drawn from food, spending, inventory, shopping, goals.
An optional expiry must include a timezone and be in the future. An optional source
message must be an owned USER message. Creation itself is the user's explicit
confirmation; model output or a saved conversation is not automatic consent.

Returns 201 `{"data":memory}`. The view contains id, type, content, topics,
source=USER_EXPLICIT, provenance=OBSERVED, confidence (exact decimal string),
source_message_id, expires_at, version, created_at, and updated_at. Confidence 1
records explicit assertion, not verification of the underlying financial claim.
Ownership/internal search columns are not returned. No profile setting is changed.

### GET /api/v1/memories

Returns 200 `{"data":[memory,...]}`. Query parameters: limit (1–100, default 20),
offset (0–10000, default 0), optional type, optional nonblank query (1000 characters),
and include_expired (default false). Without query this is a management list;
with query it is a ranked lexical/topic search. Ties use updated_at and UUID.
An empty/no-match search returns an empty list. Search text is bound as data.

### GET /api/v1/memories/{id}

Returns 200 `{"data":memory}`, including an expired record when explicitly selected.

### PATCH /api/v1/memories/{id}

Explicit replacement using the POST fields plus required positive integer
`expected_version`. Supply the desired type/content/topics/expiry/source message;
omitted optional fields reset to their POST defaults. Success returns 200 with the
version incremented. A stale version returns 409. Invalid expiry or fields return
422. An owned new source message can replace the prior source link.

### DELETE /api/v1/memories/{id}?expected_version=1

Returns 204 after deleting the owned memory, or 409 for a stale version. The version
query parameter is required and no others are accepted. This explicit API request
is the user control; it is not a model-selected tool. Deletion removes future
memory retrieval. Existing conversation responses and tool audits retain their
historical contents.

## Insights (Milestone 7)

The worker generates insights; these APIs never generate or recalculate them.
Types: SPENDING_CHANGE, UNUSUAL_PURCHASE, INVENTORY_EXPIRY. Exact rule thresholds,
calendar boundaries and source semantics are in ADR-010. No live model is required.

### GET /api/v1/insights

Returns 200 `{"data":[insight,...]}` ordered by created_at/UUID descending. Accepts
limit/offset with the same bounds as memories, optional type, and optional status
(ACTIVE, READ, DISMISSED, RESOLVED, EXPIRED). Omitting status returns only unexpired
ACTIVE/READ records. Expiry is enforced on reads even if the worker is offline.
An explicit EXPIRED query includes active/read rows whose expiry has passed.

An insight contains id, type, title, summary, source_data, calculation,
provenance=DERIVED, nullable exact confidence, status, version, created_at,
updated_at, evaluated_at, expires_at, nullable read_at and dismissed_at. Confidence
is null for financial thresholds and preserves the expiry evidence's confidence
for inventory. Source data includes the service metrics and their periods, or the
owned inventory lot projection with its original source/provenance/version.
Calculation includes the versioned rule and thresholds. Monetary and quantity
values are exact strings. No ownership IDs, delivery state or internal keys appear.

### GET /api/v1/insights/{id}

Returns 200 `{"data":insight}` including historical/inactive records. No query
parameters are accepted. Missing/foreign IDs return the same 404. Recorded evidence
is a snapshot at evaluated_at, not a claim about current stock or spending.

### PATCH /api/v1/insights/{id}

```json
{"status":"DISMISSED","expected_version":1}
```

The only user-controlled target statuses are READ and DISMISSED. An active/read
insight can be marked read or dismissed; stale versions or other transitions return
409. Repeating the current status with its current version returns the unchanged
view. Returns 200 `{"data":insight}`. The worker preserves dismissal when the same
signal is evaluated again. No public insight creation/deletion endpoint is added.

## Assistant memory and insight integration (Milestone 7)

The assistant prompt is versioned assistant.v2; the final-answer schema is unchanged.
Before the model call the service retrieves at most five relevant, unexpired owned
memories within an 8 KiB budget. Memory content is untrusted context, not instructions
or canonical financial evidence. Transcripts are never automatically saved as memory.

The registry now has fourteen read tools. get_memories requires a bounded query
and returns up to five matches under data.items, with OBSERVED provenance and each
statement's metadata. get_insights accepts limit/offset and returns current active
insights under data.items; get_insight requires insight_id and returns the full view.
Insight citations can reference data.source_data scalars using M6's grounding rules.
There are no memory write tools; explicit creation/correction/deletion uses the
memory API above. For current financial or inventory answers the assistant continues
to use the original canonical tools.

## Google Wallet (Milestone 8)

Wallet is an external projection of a canonical purchase. These routes use the
same Firebase authentication, ownership, strict validation and `Cache-Control:
no-store` rules. Missing/foreign purchase or pass IDs return identical 404 errors.
No client can supply an owner, provider identifier, amount or synchronization state.

### POST /api/v1/wallet/passes

Accepts only `{"purchase_id":"<owned purchase UUID>"}`. Returns 202
`{"data":wallet_pass}` with the existing or newly queued pass. Repeating the request
returns the same pass and preserves its current status/backoff. Purchase creation
also schedules this projection through the independent outbox subscriber, so this
endpoint can ensure a pass before the worker handles the purchase event. No Google
API call occurs here. Manual purchases without a receipt are supported.

The pass view contains id, purchase_id, provider=GOOGLE, pass_type=GENERIC,
nullable class_id/object_id, status, attempt_count, next_attempt_at, nullable
last_error_code/last_error_at/synced_at, created_at and updated_at. Owner IDs and
leases are private. Class/object IDs are assigned once configured and then remain
stable. States are PENDING, SYNCING, RETRY, SYNCED and FAILED. attempt_count is the
current cycle's count; next_attempt_at is actionable only for nonterminal states.
SYNCED records API acceptance, not proof of saving into a Google account.

### GET /api/v1/wallet/passes

Returns 200 `{"data":[wallet_pass,...]}`. Supports limit (1–100, default 20), offset
(0–10000, default 0), optional purchase_id and optional status. Ordering is
created_at/UUID descending. Ownership filters always apply; foreign filters return
an empty list. Unknown query parameters are rejected with 422.

### GET /api/v1/wallet/passes/{id}

Returns 200 `{"data":wallet_pass}`. No query parameters are accepted.

### POST /api/v1/wallet/passes/{id}/sync

Requires an empty JSON object. Returns 202 with the pass. SYNCED/FAILED passes are
queued with a fresh three-attempt budget; PENDING/RETRY/SYNCING passes keep their
existing job/backoff/lease. Provider work runs only in the worker. This also recovers
failures after deployment configuration is corrected. No query parameters accepted.

### POST /api/v1/wallet/passes/{id}/add-to-wallet

Requires an empty JSON object and a SYNCED pass; otherwise returns 409. Returns 200
`{"data":{"save_url":"https://pay.google.com/gp/v/save/<signed JWT>"}}`. Signing
uses managed server credentials outside database transactions. The JWT contains
only the stable Generic class/object references, configured signer/origins and
issuance/expiry claims. The URL is a bearer capability, never stored or logged by
Raseed. Google controls acceptance of the five-minute expiry claim and actual saving.
No query parameters accepted. No authentication token is included in the save URL.

Signing errors use the standard safe envelope: wallet_timeout (504),
wallet_invalid_response/wallet_rejected (502), or wallet_configuration,
wallet_authorization, wallet_rate_limited and wallet_unavailable (503). They do not
change canonical data or synchronization status. Worker errors use the same safe
codes plus wallet_lease_expired and are read through the pass status API. Error
responses never include provider bodies or credentials. See ADR-011 for recovery.

## Market intelligence (Milestone 9)

All routes use Firebase ownership, strict body/query validation and no-store. No
route accepts an owner, URL, freeform search query, price, product evidence or
provider choice from the client/model. Missing/foreign IDs return identical 404s.
The service preserves canonical historical prices independently of external offers.

### POST /api/v1/market/searches

Accepts exactly one of line_item_id or product_id, a required uppercase registered
two-letter country, and optional postal_code (1–20 alphanumeric/space/hyphen
characters, trimmed and uppercased). A product must be linked to an owned purchase.

```json
{"line_item_id":"<owned line UUID>","country":"US","postal_code":"10001"}
```

Returns 202 `{"data":search}` for both newly queued and reused requests. No provider
call occurs in the request. Repeating the same target snapshot and destination
reuses an owned pending/fresh search, including cached empty/failed results. A new
request is created after expiry. No query parameters are accepted.

The search view includes id, line_item_id, product_id, country, postal_code, target,
status, attempt_count, failure_code, next_attempt_at, created_at, completed_at,
expires_at and observations. Status is PENDING, PROCESSING, RETRY, SUCCEEDED or
FAILED. Ownership, fingerprint, leases and provider credentials are private.

Target includes identity (name, optional brand/GTIN/MPN/variant/pack), identity
provenance, currency, nullable recorded unit_price/pricing_unit/purchased_at and
price_provenance=OBSERVED. Product-only searches have no selected historical price
and use the owner's currency. Line searches use their canonical purchase currency.
Pack is `{quantity: decimal string, unit: g|kg|ml|l|each, count: positive integer}`.
Absent or untrusted metadata is unknown, never inferred from arbitrary item text.

### GET /api/v1/market/searches/{id}

Returns 200 `{"data":search}` with current persisted status and up to five
observations. No query parameters. A successful empty result means this bounded
provider search found no offers, not that no offers exist elsewhere. Pending and
failed requests contain no fabricated observations or comparison conclusions.

Each observation contains id, search_id, nullable matched product_id, provider,
provenance=EXTERNAL, offer, fetched_at, effective expires_at, stale and comparison.
The offer retains name/brand/GTIN/MPN/variant/pack, offer_id, source, merchant, HTTPS
URL, nullable seller location and delivery_country, observed_at, optional provider
expires_at, exact price/currency, nullable shipping/tax, condition and availability.
Monetary values serialize as exact strings. URLs are source references, not fetched
by the API or assistant. Do not render external text as executable HTML.

Comparison contains matching (EXACT/UNCERTAIN/MISMATCH, rule confidence, versioned
rule, DERIVED provenance), comparable, reasons, conclusion, nullable exact
display_price_difference (external minus historical unit price), provenance=DERIVED
and checkout_savings_known=false. LOWER_DISPLAY_PRICE, EQUAL_DISPLAY_PRICE or
HIGHER_DISPLAY_PRICE require all compatibility/freshness gates. Otherwise conclusion
is NOT_COMPARABLE with reasons such as identity_not_exact, unknown_pack,
pack_mismatch, no_historical_unit_price, unsupported_pricing_unit, currency_mismatch,
delivery_not_confirmed, condition_not_new, stock_not_confirmed or stale_observation.
These results never establish all-in checkout savings or currency conversion.

Observations expire fifteen minutes after observed_at, capped by earlier provider
expiry. Fetching an older price never renews its age. Search caching ends at the
earliest observation expiry, or fifteen minutes after an empty success/failure.
Expired observations remain readable as historical evidence with comparisons blocked.

### POST /api/v1/market/searches/{id}/retry

Requires `{}` and no query parameters. Returns 202 after requeuing an owned FAILED
request with a new three-attempt budget. Returns 409 if not failed or a newer active
request has the same fingerprint. Transient retries otherwise use persisted
5/10-second backoff and bounded Retry-After; callers cannot bypass active backoff.
Failure codes include market_configuration, market_authorization,
market_unavailable, market_timeout, market_rate_limited, market_invalid_data,
market_rejected and market_lease_expired. No provider diagnostics are exposed.

### GET /api/v1/market/observations/{id}

Returns 200 `{"data":observation}` including stale evidence and its current
comparison eligibility against the original canonical target snapshot. No query
parameters. Ownership is checked through both observation and search.

### Assistant tools

search_market_prices takes the POST search fields; get_market_search takes only
search_id. Both use MarketService and the existing audited tool boundary. The
registry has sixteen tools and prompt assistant.v3. The model obtains line/product
IDs from purchase tools and asks for missing destination context. It reports pending
work without polling repeatedly and can read completion on a later turn. Only
validated service conclusions and cited external source/time data support a lower
displayed-price explanation. No general web access or financial write is enabled.
