# Workflow — Market price lookup and comparison

1. Identify an owned purchase line through existing purchase history/detail, or a
   product linked to an owned line. Obtain an explicit destination country and,
   optionally, postal code. Do not infer geography from the user's currency.
2. Submit search_market_prices or POST /api/v1/market/searches. The service captures
   canonical identity and historical price context, authorizes ownership and reuses
   a pending/fresh search when available. Otherwise the request and outbox event
   commit together. API/tool execution makes no market network call.
3. The separate worker claims the request with a five-minute lease, calls the
   bounded MarketProvider outside DB transactions and validates the complete result.
   Malformed offers fail the batch without partial persistence.
4. Observations, original source/time/location/URL/pack fields, exact prices,
   derived matching evidence and completion acknowledgement commit atomically.
5. GET search or get_market_search returns status, evidence and deterministic
   comparisons. Stale, uncertain and incompatible observations explain why a
   comparison is unavailable. Product-only searches display observations without
   inventing a historical baseline.
6. The assistant may explain a lower displayed price only when the service returns
   that conclusion. Cite source/time and distinguish historical purchase prices
   from external displayed prices, shipping and tax. No unqualified checkout-saving
   claim is supported. A pending result is reported as pending without busy-polling.

Transient provider failures get at most three attempts with 5/10-second backoff and
bounded Retry-After. Permanent/exhausted failures stay visible; an owned explicit
retry can reset the attempt cycle. Crashes recover after lease expiry; stale workers
cannot finalize or duplicate observations. No purchase, inventory, Wallet, budget
or notification state is changed. See ADR-012 for exact matching/freshness semantics.
