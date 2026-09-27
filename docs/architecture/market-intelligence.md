# Raseed V2 Market Intelligence

## Scope

This subsystem answers questions that require current external information, such as:

- “Can I get this product cheaper?”
- “What is the current price of a comparable product?”

## Boundary

Internal Raseed purchase history and external market observations are separate data domains.

User purchase:
- source = user's receipt
- historical fact

Market observation:
- source = external provider
- observed_at timestamp
- merchant/source/location/pack-size context

## Flow

Assistant intent → identify product → external search/lookup adapter → normalize candidate offers → compare like-for-like → persist optional observation → LLM explanation.

## Guardrails

- Never compare different pack sizes without making that explicit.
- Preserve observation timestamp.
- Preserve source/provider and location where applicable.
- Separate displayed price from shipping/tax when possible.
- Do not state that a price is “current” without a recent observation.
- External web content is untrusted input.

## Milestone 9 implementation

[ADR-012](../decisions/ADR-012-market-intelligence.md) defines the concrete request,
provider, freshness, matching and comparison contracts. The existing monolith and
worker remain in place. MarketService authorizes an owned line or previously
purchased product, captures a canonical target snapshot, and atomically creates a
MarketSearch and MARKET_SEARCH_REQUESTED outbox event. Repeated requests reuse
the same owner's pending or fresh search. Network I/O runs only in MarketProcessor.

MarketProvider accepts identity and destination data. The first eBay Browse adapter
uses configured application credentials, fixed endpoints, five candidate details,
bounded HTTP responses/timeouts and classified errors. It does not send purchase
prices, receipt contents or owner identifiers to the provider. It never follows
listing-supplied API URLs. Google Wallet is unaffected.

MarketPriceObservation retains relational price/source/time/location fields and
bounded identity/pack/availability evidence, with EXTERNAL provenance. Matching
status, confidence and versioned rules are persisted as DERIVED evidence. Only
observed product identifiers may support an exact match; name overlap is uncertain.
Pack quantity and count must be explicit. Equivalent kg/g and l/ml units normalize
exactly; differing pack composition, currency or pricing basis blocks comparison.

The service reports a lower displayed price only for exact, compatible, fresh,
new/in-stock offers with confirmed destination. It never claims all-in checkout
savings. Shipping/tax are separate nullable external facts, and purchase unit_price
remains a historical observed fact. Missing unit_price is not reconstructed from
line totals. Product-only searches have no chosen historical price baseline.

Effective observation expiry is fifteen minutes after observed_at, capped by any
earlier provider expiry. Expired observations remain readable but cannot support
comparisons; fetching old data does not renew freshness. Empty successes are cached
for fifteen minutes. Expired searches create new requests and retain old evidence.

The API and two approved assistant tools queue/read this flow. Pending results have
no inferred prices; users can read completion in a later request or assistant turn.
The model sees structured evidence, never unrestricted browsing or database access.
