# Milestone 5 validation checkpoint

Validated on 2026-09-26 from M4 checkpoint `04a2777`.

## Result

Financial analytics is implemented as authenticated read services within the
existing modular monolith. Four APIs provide spending summaries, category and
merchant breakdowns, and period comparisons. Existing purchase history gains
typed filters while preserving its response shape and all-time default.
ADR-008 and the API contract specify the implemented financial semantics.

Calculations use canonical Purchase, LineItem, Merchant, Category, and Payment
data. Totals remain exact and separate by currency. Local calendar boundaries,
known/unknown line amounts, payment evidence, pagination, and rounded ratios have
explicit deterministic rules. No LLM or extraction output calculates these metrics.

| Check | Result |
| --- | --- |
| Complete Python suite with PostgreSQL | 443 passed, zero skipped |
| New analytics tests | 104 passed: 57 validation/authentication, 47 integration |
| Additional M5 migration preservation test | Passed |
| Backend coverage | 97% |
| Analytics service and repository coverage | 100% |
| Ruff check | Passed |
| Ruff format --check | Passed, 74 files |
| mypy backend | Passed, 53 source files |
| Development Alembic upgrade/current | 0005_financial_analytics (head) |
| Alembic check | No schema drift |
| Real PostgreSQL loopback HTTP smoke | All four analytics APIs and filtered purchase history passed |
| PostgreSQL EXPLAIN | All five new index access paths verified |

Commands run:

```powershell
uv run --env-file .env pytest --cov=backend/app --cov-report=term-missing
uv run ruff check backend tests database
uv run ruff format --check backend tests database
uv run mypy backend
uv run alembic upgrade head
uv run alembic current
uv run alembic check
```

The full suite includes the HTTP smoke. Targeted analytics and migration checks
also passed (109 tests). Test-only injected authentication and a fixed clock make
the API fixtures repeatable; PostgreSQL and HTTP transport are real. No provider
or cloud account was contacted. The two existing dependency warnings remain:
Starlette/httpx deprecation and Google's Python 3.10 support notice.

## Evidence and migration

Tests cover every supported filter, cross-user and missing catalog selections,
unknown input/SQL rejection, exact six-place and oversized aggregate amounts,
split payments without row multiplication, missing payment instruments, independent
line/purchase category bases, hierarchy metadata, unknown values, merchant UUID
identity, zero denominators, mixed/missing currencies, stable pagination, and
half-open date boundaries. DST, leap months, year transitions, ambiguous/skipped
midnights, and database-session timezone differences are exercised.

A comparison test commits a new purchase and preference change through a second
connection between aggregate reads. The response retains its original snapshot;
the next request observes the commits. Read-only/repeatable-read settings do not
change the default isolation of subsequent write transactions.

The HTTP fixture produces exact INR 13.60 across four owned purchases and a
separate USD total, with another owner's large purchases excluded. It exercises
all analytics APIs, history filters, authentication rejection, and owner isolation.

Development PostgreSQL uses loopback port 55432. Destructive migration/truncation
tests use only the separate `raseed_test` database. The M5 downgrade/upgrade test
preserves full identity, category, purchase, line, payment, inventory, and outbox
records. The development database was upgraded without a downgrade.

EXPLAIN verified owner/currency/date, owner/merchant/date, owner/category/date,
product-history, and line-category-history access through the new indexes. The
read-only check disabled sequential scans locally because the synthetic dataset
is small; this verifies usable access paths, not production-scale latency.

## Files changed

Application:

- `backend/app/analytics/__init__.py`
- `backend/app/analytics/money.py`
- `backend/app/analytics/repository.py`
- `backend/app/analytics/schemas.py`
- `backend/app/analytics/service.py`
- `backend/app/api/analytics.py`
- `backend/app/api/purchases.py`
- `backend/app/main.py`
- `backend/app/purchases/models.py`
- `backend/app/purchases/queries.py`
- `backend/app/purchases/repositories.py`
- `backend/app/purchases/service.py`

Migration and tests:

- `database/migrations/versions/0005_financial_analytics.py`
- `tests/test_analytics_integration.py`
- `tests/test_analytics_validation.py`
- `tests/test_migrations.py`

Documentation:

- `DEVELOPMENT.md`
- `docs/README.md`
- `docs/api/api-contract.md`
- `docs/data/database.md`
- `docs/decisions/ADR-008-financial-analytics.md`
- `docs/implementation/roadmap.md`
- `docs/implementation/milestone-5-validation.md`
- `docs/workflows/financial-queries.md`

## Boundaries and deferrals

Budget persistence remains deferred as required by the existing blueprint.
Recurring-pattern inference, currency conversion, refunds/credits, implicit
category hierarchy roll-ups, and allocation between line and purchase totals have
no approved M5 semantics and are not invented. Nonexistent local-midnight or
unrepresentable date boundaries return 422 instead of silently changing dates.

No Milestone 6 assistant/tool gateway, insights, memory, inventory changes,
scheduled analytics, Wallet, market intelligence, notifications, frontend redesign,
or legacy migration is included. The migration changes indexes only; no new
financial persistence entity or outbox consumer is introduced.
