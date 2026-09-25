# ADR-005 — Milestone 2 canonical receipt and purchase foundation

## Status

Accepted implementation clarification of the approved Milestone 2 scope.

## Scope and ownership

The eight documented entities are implemented using SQLAlchemy/PostgreSQL and
Alembic revision `0002_purchase_foundation`, after the unchanged identity revision.
`domain-model.md` remains authoritative: separate `entities.md` and
`relationships.md` files are not present in this repository.

Receipts and purchases belong to one user. Extraction runs inherit ownership
through their receipt; line items and payments inherit it through their purchase.
All these repositories require `CurrentUser` and scope every read by ownership.
A composite foreign key prevents a purchase from referencing another user's
receipt, including when inserting outside the application service. At most one
canonical purchase references a receipt; manual purchases may have no receipt.

Merchants, categories, and products are shared canonical reference data, as their
approved fields contain no user owner. Creation/read services require authenticated
context but are internal only: no catalog mutation API is exposed. Raw merchant
and item text stays on user-owned purchases/line items. Merchant normalization is
Unicode NFKC, whitespace collapse, and case-folding; normalized names are indexed,
not unique (different merchants can share a name). Category slugs are globally
unique. No taxonomy is seeded: the current specification defines no required
category names. Categories support parent links; creation only references existing
parents, and no reparenting API is introduced.

## Metadata and provenance

Metadata creation is not an upload. Add `PENDING_UPLOAD` before the existing
receipt lifecycle. The metadata-only API sets that state and leaves storage URI,
uploaded_at, and processed_at null. It cannot set storage locations, processing
state, or execution results. A claimed SHA-256 content hash (64 lowercase hex
characters) is unique per user; the same hash is permitted for different users.
Milestone 3 must verify client-claimed size/hash/MIME against the actual artifact.
Duplicate metadata returns 409 rather than silently replacing an existing row.

Extraction runs are separate provenance records, never canonical financial data.
Their states are PENDING, RUNNING, SUCCEEDED, FAILED. Pending runs have no execution
timestamps; running runs have started_at; terminal runs have both timestamps.
Outputs/errors are nullable JSONB/text and no model is invoked by persistence.
Receipt status transitions and extraction orchestration remain Milestone 3.

## Exact financial data

Money and quantities use NUMERIC(20,6) and Python Decimal. Inputs accept decimal
strings, integers, or Decimal, never binary floats, booleans, NaN or infinity.
Excess scale/precision is rejected before persistence rather than rounded.
Amounts are nonnegative; quantities/payments, when present, must be positive.
Refund/credit modeling is not introduced here.

Currency, purchased_at (timezone-aware), merchant_name_raw, purchase_type,
payment_status, and grand_total are explicitly supplied. Subtotal, discount, tax,
and shipping may be null when unknown; they have no zero defaults. Quantity,
unit_price, and line_total may likewise be unknown; none is fabricated from the
others. No inferred product association is required. When every total component
is supplied, subtotal - discount + tax + shipping must equal grand_total.
Line multiplication is not assumed: receipt discounts and rounding may differ.

Payment currencies must equal purchase currency; supplied payments cannot exceed
grand_total. Status is UNKNOWN, UNPAID, PARTIALLY_PAID, or PAID. If payment records
are supplied, they must agree with the declared status. A receipt can declare
PAID without recording a payment instrument. Only a four-digit last4 is supported;
there are no PAN, CVV, token, or payment-credential fields. Provider/reference
fields are opaque identifiers and must not contain credentials or card numbers.

## Transactions, indexes, and deletion

Purchase, line items, payments, and one PURCHASE_CREATED outbox event commit in a
single transaction. The outbox foundation is required by the existing database
contract and roadmap, not a new integration. It stores ownership, purchase linkage,
event type, a minimal ID-only payload, timestamps, and uniqueness per purchase/event.
No queue, dispatcher, worker jobs, upload event, or external calls are implemented.
Metadata creation does not emit RECEIPT_UPLOADED because no file was uploaded.

User→receipt/purchase deletion is RESTRICT. Purchase→receipt and all catalog
references are RESTRICT. Receipt→extraction runs and purchase→line items/payments
are CASCADE because those rows are owned children; purchase→outbox is RESTRICT to
preserve durable events. Category parent deletion is RESTRICT. No deletion API is
exposed. Indexes cover user/time/id listing, child foreign keys, catalog lookups,
and unpublished events. User-scoped duplicate hash and receipt-purchase constraints
provide race-safe duplicate protection.

## API

Only metadata POST and receipt/purchase GET endpoints are added. Purchase creation
and catalog/provenance writes remain typed internal service operations, ready for
Milestone 3. Lists use bounded limit/offset and stable timestamp/UUID ordering.
Missing and cross-user IDs both return 404 to avoid revealing another user's data.
Public receipt views omit internal storage URI and user ownership identifiers.
Money and quantities serialize as decimal strings. See the API contract.
