# ADR-013 — Product interface and minimal read contracts

The requested M10 is the product UI milestone; operational hardening remains a
later milestone. The Next.js App Router and Firebase identity boundary remain.
The web app uses a dedicated typed API client, shared design tokens/components,
owned browser-session state and real service results. It does not recalculate
spending, price comparisons, inventory balances or insights. Amounts stay decimal
strings, unknowns stay unknown, and external/estimated evidence is labeled.

Three additive read contracts close necessary UI gaps without changing domain
semantics or persistence:

- GET purchases accepts optional `query`, 1–200 nonblank characters, a literal
  case-insensitive substring of merchant_name_raw or a line's raw_name. Wildcards
  are escaped; it combines with existing filters and pagination. Analytics does
  not accept it and the frontend does not derive filtered spending totals.
  Assistant history arguments retain their existing schema through a typed adapter;
  the UI search field does not implicitly expand the model's tool contract.
- GET receipts/{id}/file authorizes the owner before storage access, returns the
  original image/PDF bytes with the recorded MIME, no-store and nosniff, and an
  attachment filename. Missing/foreign/not-uploaded receipts return 404. Storage
  reads occur outside a DB transaction. No public URL or storage reference is
  exposed. The browser uses short-lived in-memory blob URLs and revokes them.
- GET assistant/conversations returns owned conversations ordered by updated_at
  and UUID descending with existing limit/offset bounds. It invokes no model.

The product routes are Overview, Purchases, Analysis, Inventory, Insights, Assistant,
Wallet and Settings, with a persistent Add Receipt action. Small screens use an
accessible navigation drawer. Receipt polling is bounded and offers manual refresh;
NEEDS_REVIEW never promises an unimplemented correction endpoint. Inventory edits
use versioned/idempotent events. Assistant responses and evidence are escaped text;
no frontend answer generation or unrestricted tool execution is introduced.

Tests substitute identity/provider interfaces in isolated browser contexts and
intercept loopback API transports; PostgreSQL integration tests separately verify
the real backend boundaries. Production Firebase verification is unchanged.
No legacy Streamlit, new budgeting, notification or analytics architecture work.

## Product redesign read contracts

The redesigned Overview and Analysis need a time series and payment distribution.
Two additive reads extend the existing AnalyticsService/repository; no persistence,
authentication, assistant tool contract or financial rule changes:

- `GET /analytics/spending-trend` accepts AnalyticsQuery. It groups owned purchase
  grand totals by local calendar day for ranges up to 62 days, otherwise month.
  Ranges longer than 3660 days return 422 to bound the series. Empty buckets are
  zero-filled per represented currency (or the explicitly selected currency).
  Partial months include only purchases within the requested half-open interval;
  the bucket date is the month's first day. Whole current periods follow ADR-008.
- `GET /analytics/spending-by-payment` accepts AnalyticsQuery. It groups recorded
  Payment amounts by method and currency, joined only to matching owned purchases.
  Shares use recorded payments in that currency, with null for a zero denominator.
  Missing payment records are not imputed from purchase totals. No instrument
  references or last-four digits are returned.

Both return DERIVED metadata, exact decimal strings and the resolved period and
filters in the normal no-store envelope. Existing read-only repeatable-read
snapshots and ownership predicates apply. SVG geometry uses numeric projections
only; displayed totals, shares and changes come from the backend. Charts include
accessible exact values. Category comparisons reuse the existing category endpoint
with the comparison service's resolved date boundaries.
