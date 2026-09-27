# ADR-012 — On-demand market intelligence

## Scope and architecture

M9 implements the approved external-search flow in the modular monolith and
existing separate worker. Canonical purchases/products and external prices remain
separate. No Wallet, analytics, budgeting, notification or UI redesign is included.

The blueprint defines observations but not durable search request fields. A
`MarketSearch` request row is added explicitly to retain owned target/context,
empty results, asynchronous status, cache lifetime, retries and leases. Its
`MARKET_SEARCH_REQUESTED` outbox event commits in the same transaction. This avoids
using an observation as a placeholder price or overloading outbox JSON with mutable
request state. `MarketPriceObservation` stores actual external offers only.

MarketProvider receives a bounded product identity and destination, never purchase
amounts, receipt content, owner IDs, credentials chosen by a model, or arbitrary
URLs. The initial eBay Browse REST adapter uses a configured application OAuth token
and an explicit marketplace. Fixed eBay endpoints, no redirects, five candidates,
bounded response sizes/timeouts and classified errors isolate network access.
Tests inject deterministic providers and mock HTTP; no live account is required.

## Target and matching

Search accepts exactly one owned line_item_id or previously purchased product_id,
plus explicit destination country and optional postal code. A product-only search
has no selected historical price. A line uses its canonical purchase currency and
recorded unit_price/unit; it never substitutes grand_total or assumes line_total
divided by quantity equals unit_price. Product searches use the owner's currency.
Product IDs must be linked to an owned purchase; missing/foreign targets return 404.

Existing Product metadata is the optional identity evidence contract: gtin, mpn,
variant, pack={quantity, unit, count}, with identity_source=OBSERVED. No new product
association is written. Ingested observed GTIN metadata remains compatible. Pack
data absent from existing ingestion stays unknown; it is never guessed from names.

Checksum-valid GTINs normalize to fourteen digits. Exact GTIN or exact observed
brand+MPN supports identity matching; contradictory IDs/brand/variant reject it.
Name overlap is only UNCERTAIN, never evidence for a lower-price conclusion.
Rule confidence (1 for exact, 0.5 for uncertain, 0 for mismatch) describes the
deterministic matching rule, not a calibrated probability. Matching provenance is
DERIVED; source product evidence is OBSERVED and offer evidence is EXTERNAL.

Comparison requires exact identity, known equal packs, a canonical per-each pricing
unit, same currency, NEW condition, confirmed stock and matching delivery country.
Pack quantity and count must both be explicit. kg/g and l/ml normalize exactly;
different dimensions or total pack sizes are not comparable. Contradictory pack
descriptions under the same GTIN are rejected. Missing metadata is not a match.
The eBay adapter uses explicit structured aspects for pack quantity/unit/count;
incomplete listing metadata therefore often yields observations without comparison.
Multi-item lots leave pack composition unknown because listing aspects may describe
one item rather than the complete lot. Invalid optional canonical metadata is
discarded as matching evidence without blocking the bounded name lookup.

## Prices, provenance and freshness

Observations retain provider/offer ID, source, merchant, HTTPS URL, seller location,
delivery country, observed_at, fetched_at, expires_at, identity/pack fields,
condition/stock, exact displayed price/currency and nullable shipping/tax. All
amounts use NUMERIC(20,6), never floats. Provider data is validated as a whole before
persistence; malformed/duplicate conflicting offers fail without partial results.
No missing cost is zero, no currency conversion occurs and canonical rows never change.

Comparison reports LOWER/EQUAL/HIGHER_DISPLAY_PRICE only for compatible fresh
offers. It never asserts an unqualified cheaper checkout price. Shipping/tax may
be unknown and the historical unit price's tax/discount basis is not established.
Exact display-price differences are DERIVED. Every unavailable comparison includes
reasons; stale observations remain historical evidence with no price conclusion.

The docs specify recency but no duration; M9 uses fifteen minutes from observed_at,
capped by any earlier provider expiry. Timestamps must be timezone-aware and not
in the future. Retrieval time never refreshes an old provider observation. eBay
has no price-observation timestamp, so successful retrieval is explicitly the
observation time, not a seller price-change time.

Identical owner/target-snapshot/destination searches reuse pending jobs and completed
fresh results (including empty results). Cache lifetime is at most fifteen minutes
after completion and no later than the earliest observation expiry. Failed jobs
are retained for fifteen minutes to prevent request loops; explicit retry is allowed.
Expired cache causes a new request/event and retains previous observations. Owner
serialization and an active-fingerprint unique index make concurrent requests safe.

## Worker and APIs/tools

Claims use five-minute leases and random tokens; provider I/O holds no database
transaction. Up to three attempts use 5/10-second backoff and bounded Retry-After.
Transient transport/timeout/408/429/5xx failures retry; configuration, authorization
and malformed data fail durably. Observation insertion, completion and outbox
acknowledgement commit atomically. Stale workers cannot commit; uncertain outcomes
and crashes repeat read-only lookup without duplicate observations. Requeue resets
only failed requests and checks for a newer active request with the same fingerprint.

POST /api/v1/market/searches queues or reuses a search; GET /{id} returns status,
target, observations and comparisons; POST /{id}/retry explicitly requeues failure.
GET /api/v1/market/observations/{id} returns owned historical evidence/comparison.
All use existing authentication, strict bodies/query validation and no-store.

The approved external tool search_market_prices uses the same service; it queues
work or returns cache immediately. get_market_search reads an owned result. These
tools do not mutate financial data. The assistant identifies line/product IDs using
existing purchase tools, asks for missing destination context, and reports pending
work without busy-polling. A later turn can read completion. It cites exact service
values/source/time and obeys comparison reasons; it cannot browse arbitrary web
content or manufacture a price. Prompt assistant.v3 keeps the existing grounding
and audit boundary. No other assistant redesign is introduced.

## Migration and deferrals

0009_market_intelligence adds search/observation tables, owned composite FKs,
outbox request link/event support, unique keys and ready/cache/owner indexes.
M1–M8 records and subscriber acknowledgements survive upgrade/downgrade. Downgrade
discards only M9 requests/events/observations; destructive tests use a disposable DB.

Live eBay access/coverage, additional providers, pack enrichment/user confirmation,
cross-pack substitutes, all-in checkout savings, currency conversion, automatic
background recommendations, managed task deployment, notifications and UI are deferred.
