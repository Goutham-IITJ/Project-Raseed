# ADR-008 — Deterministic financial analytics

## Status and scope

Implementation clarification for the requested Milestone 5, within the approved
modular monolith, PostgreSQL, authenticated repositories, and exact-money model.
The roadmap defines summary, category, merchant, and period-comparison capabilities
but leaves their concrete read contracts unspecified. This ADR and the API contract
specify those reads. No new persisted entity, event subscriber, or provider is needed.

## Financial meaning

Spending is SUM(Purchase.grand_total), dated by purchased_at, including every
payment status. It measures recorded purchases, not cash flow. All results are
DERIVED from canonical records; receipt metadata and ExtractionRun output never
enter analytics. Each currency has independent totals; omitting a currency filter
returns every represented currency, never an exchange-rate conversion or a sum
across currencies. An explicitly selected currency has a zero summary when empty.

Summary metrics include purchase count, total, average, minimum/maximum, first/last
purchase timestamps, and recorded-payment total/count/covered purchase count.
Payments are aggregated per purchase before joining, so multiple instruments or
line items cannot multiply purchase amounts. No instrument data is returned in
analytics. A PAID purchase can have no Payment rows: recorded payments are evidence
coverage, not an assertion of actual paid or outstanding amounts. Payment metrics
use the linked purchase's period, not the instrument record's creation timestamp.

Category breakdown has two explicit bases. `purchase` groups grand_total by the
direct Purchase.category_id and reconciles with spending. `line_item` groups only
recorded LineItem.line_total by the direct LineItem.category_id. It reports known
and unknown amount counts; an entirely unknown group has null total. No quantity
multiplication, product-category fallback, tax/discount allocation, or reconciliation
between these bases is invented. Purchase counts within line groups are distinct
and are not additive across categories. Missing associations have a null category
bucket. Parent IDs are returned, but no implicit hierarchy roll-up occurs.

Merchant analysis groups by canonical merchant UUID, with one null bucket for
unassociated purchases. Equal names do not merge distinct canonical merchants.
Catalog names are returned only through the current user's qualifying purchases.
Breakdown shares use the full known total in the same currency before pagination;
zero or unknown denominators produce null shares.

PostgreSQL NUMERIC sums and integer/Decimal application arithmetic retain all six
canonical decimal places and permit aggregate totals larger than one stored amount.
Only averages and percentages require rounding: six decimal places, ROUND_HALF_EVEN,
performed from exact integer ratios. Computation is independent of Python's ambient
Decimal context. Comparison deltas are exact; percentage change is null whenever
the comparison total is zero, including zero-to-zero.

## Periods and history

Explicit YYYY-MM-DD ranges are half-open [start_date, end_date) in the authenticated
user's current IANA timezone. Both dates are required together. Their UTC boundaries
are returned and used directly against indexed purchased_at; the database session
timezone and ingestion/creation timestamp do not select the period.

Allowlisted periods are today, yesterday, this_week, last_week, this_month,
last_month, this_year, and last_year. Weeks start Monday. These denote whole local
calendar periods, including the remaining part of a current week/month/year.
Analytics defaults to this_month; unfiltered purchase history remains all-time.
The clock is read once per operation and is injectable for deterministic tests.
Local days can span 23 or 25 hours. Ambiguous midnight uses its earliest UTC instant;
a nonexistent midnight/skipped date or an unrepresentable UTC boundary returns 422
instead of silently moving a requested boundary.

Comparisons accept an explicit second date pair. Otherwise named periods compare
with the preceding calendar day/week/month/year; custom ranges compare with the
preceding equal number of local calendar days. Different-length explicit periods
are allowed and reported, without daily normalization or annualization. Currency
sets are the union of both periods, with zero metrics for the missing side.

Existing GET /purchases gains typed date/period, currency, merchant, purchase
category, line-item category, product, purchase-type, and payment-status filters.
`category_id` always means the direct purchase category. `line_item_category_id`
and `product_id` must match the same line when both are supplied. EXISTS predicates
select a purchase once, and its full canonical children are returned. In a
line-item breakdown these filters also restrict the contributing lines. All other
analytics filters select whole purchases. No arbitrary expression or SQL is accepted.

## Authorization, consistency, and indexes

Every query starts from Purchase.user_id supplied by CurrentUser. Child queries
join that owned purchase scope. Missing or another user's catalog selection yields
the same empty result; shared catalog existence is not independently disclosed.
Existing purchase detail ownership/404 behavior is retained.

Analytics operations use a read-only REPEATABLE READ transaction after the existing
identity transaction. Preferences, both comparison periods, and aggregate queries
therefore share a snapshot. Default READ COMMITTED behavior for existing writes is
unchanged. Queries remain bounded by ownership and typed filters; group/history
pages use the existing limit/offset bounds and deterministic UUID tie-breakers.

Revision 0005_financial_analytics adds owner/currency/time, owner/merchant/time,
and owner/category/time indexes and replaces standalone line product/category
indexes with (product_id, purchase_id)/(category_id, purchase_id) indexes for
history EXISTS predicates. Existing owner/time and child purchase indexes remain.
Upgrade/downgrade changes only indexes, preserving all M1–M4 records.

## Deferrals

Budget persistence and set_budget still require the later design decision stated
in the domain model/workflows. Recurring-pattern detection has no approved M5
semantics and remains with later financial/insight work. Assistant tools, insights,
memory, inventory changes, scheduled analytics, Wallet, market data, notifications,
UI work, refunds/credits, and currency conversion are outside this milestone.
