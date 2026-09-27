# Milestone 9 validation checkpoint

Validated on 2026-09-27 from M8 `40f41d7`.

## Result

M9 implements owned asynchronous MarketSearch requests, persisted external
MarketPriceObservation evidence, a typed MarketProvider boundary and an eBay
Browse REST adapter. The existing worker performs external lookups outside
database transactions. Authenticated APIs queue, read and retry requests and
read observations; the approved assistant tools search_market_prices and
get_market_search use the same owned service. Prompt assistant.v3 retains the
existing grounding and tool audit boundary.

Purchase data remains canonical and unchanged. Searches capture the chosen
historical line price and product identity; product-only requests have no
historical price baseline. Exact observed GTIN or brand/MPN supports matching;
name overlap is uncertain. Invalid optional catalog evidence stays unknown.
Comparisons require explicit equivalent pack composition, compatible pricing
units, the same currency, fresh evidence, confirmed destination and new/in-stock
offers. Mass and volume units normalize exactly without comparing different
packs. Multi-item eBay lots retain unknown pack composition.

Observations retain source/provider/offer identity, merchant, URL, location,
observed/fetched/expiry times, exact displayed prices and nullable shipping/tax.
Matching confidence and versioned rules are DERIVED; offer evidence is EXTERNAL.
The service reports only lower/equal/higher displayed prices or NOT_COMPARABLE
with reasons. It never claims checkout savings or reconstructs historical unit
prices from line totals.

Request and outbox event commit atomically. Owner/target/destination caching
reuses pending and fresh requests, including empty and failed results. Evidence
expires fifteen minutes after observation or at an earlier provider expiry;
retrieval does not refresh old evidence. Three attempts, 5/10-second backoff,
bounded Retry-After, five-minute leases, token fencing and explicit failed-request
retry handle failures and crashes. Results and acknowledgement commit together.

See [ADR-012](../decisions/ADR-012-market-intelligence.md),
[the workflow](../workflows/market-intelligence.md) and
[the API contract](../api/api-contract.md#market-intelligence-milestone-9).

## Validation

| Check | Result |
| --- | --- |
| `uv run pytest` | 900 passed, zero skipped; 254.38 seconds |
| M9 market tests | 129 passed within the complete suite |
| `uv run ruff check backend tests database` | Passed |
| `uv run ruff format --check backend tests database` | Passed; 149 files |
| `uv run mypy backend` | Passed; 103 source files |
| `uv run alembic upgrade head` | Passed |
| `uv run alembic current` | `0009_market_intelligence (head)` |
| `uv run alembic check` | No schema drift |

Tests use real disposable PostgreSQL, deterministic fake market providers and
mocked eBay HTTP transport. No live market credentials or requests are required.
Coverage includes exact/uncertain/conflicting product matching, pack/unit/currency
differences, missing historical prices, source/time provenance, stale/future
evidence, empty results, ownership, database constraints, concurrent caching,
provider errors, rate limits, retries/exhaustion/manual recovery, lease fencing,
atomic persistence/crash recovery, malformed/deeply nested provider payloads,
invalid catalog metadata and grounded asynchronous assistant invocation.

The suite retains the two existing dependency warnings for Starlette/httpx and
Google's Python 3.10 support. The test command exports only TEST_DATABASE_URL
from the ignored local `.env`; application settings use the existing loader.
This avoids the installed uv version's embedded-JSON quote handling in
`--env-file` without changing configuration or skipping PostgreSQL tests.

## Migration and changed scope

Revision `0009_market_intelligence` adds search/observation tables, ownership
foreign keys, lifecycle/provenance constraints, cache/dispatch indexes and the
outbox request link/event. PostgreSQL downgrade/upgrade tests preserve canonical
records, Wallet passes and earlier subscriber acknowledgements. Downgrade removes
only M9 requests, observations and events. Destructive migration tests run only
on the disposable database; the application database received an upgrade only.

Changes are confined to the market module/API, shared worker/configuration/model
wiring, two assistant tools and prompt version, migration and compatibility tests,
and authoritative documentation. Legacy Streamlit, Wallet behavior, analytics,
budgeting, notifications and UI implementation are unchanged.

## Deferred

Live eBay validation and additional regional providers (including Indian retail
coverage), catalog pack enrichment/confirmation, cross-pack substitutions,
checkout savings, currency conversion, automatic recommendations, managed worker
deployment, notifications and the UI milestone remain outside this change.
The first adapter supports configured EBAY_US/GB/DE/AU marketplaces and requires
the destination to match. Missing or expired application tokens fail visibly;
credentials can be replaced before an explicit retry. Incomplete listing/catalog
pack evidence intentionally returns observations without a price conclusion.
