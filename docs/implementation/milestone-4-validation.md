# Milestone 4 validation checkpoint

Validated on 2026-09-25 from M3 checkpoint
`867091dfd9dd214310eb70dc49ec8c95feaf4dc5`.

## Result

Inventory is implemented within the existing modular monolith and local outbox
worker. PURCHASE_CREATED drives explicit eligibility, unique purchase-line lots,
append-only PURCHASED events, and atomic INVENTORY_CHANGED entries. Read APIs
derive balances and expiry from history. Owned user commands record consumption,
expiry, discard, return, adjustment and correction without rewriting purchases.
ADR-007 and the inventory workflow document the implemented contract.

| Check | Result |
| --- | --- |
| Complete Python suite with PostgreSQL | 338 passed, zero skipped |
| PostgreSQL integration tests within the suite | 120 passed |
| New inventory tests | 68 passed (40 validation, 28 integration) |
| Additional M4 migration round trip | Passed |
| Backend coverage | 97% |
| Inventory API coverage | 100% |
| Ruff check | Passed |
| Ruff format --check | Passed, 64 files |
| mypy backend | Passed, 46 source files |
| Development Alembic upgrade/current | 0004_inventory (head) |
| Alembic check | No schema drift |
| Real loopback HTTP smoke | Upload → extraction → purchase → lot → consumption → balance 1 |

Commands run:

```powershell
uv run --locked --env-file .env pytest --cov=backend/app --cov-report=term-missing --tb=short
uv run --locked ruff check backend tests database
uv run --locked ruff format --check backend tests database
uv run --locked mypy backend
uv run --locked alembic upgrade head
uv run --locked alembic current
uv run --locked alembic check
```

Targeted inventory and migration tests were also run while implementing. Local
PostgreSQL used host port 55432; destructive tests used only `raseed_test`, separate
from development `raseed`. The HTTP test uses fake authentication/extraction and
real private local storage. No live AI/cloud account is needed for inventory.
Two existing dependency warnings remain: Starlette/httpx deprecation and Google's
Python 3.10 support notice. Neither is an inventory failure.

Tests verify catalog eligibility and unknown values, product/unit grouping,
ownership, pagination, exact quantities, every supported action, expiry evidence
and local-date status, immutable history, no automatic expiry depletion,
concurrent delivery/enrollment/removal, idempotency replay/conflicts, rollback of
inventory and outbox together, bounded retries, terminal failures, explicit
recovery, database constraints, and migration preservation of canonical purchases.

## Files changed

- `backend/app/inventory/__init__.py`
- `backend/app/inventory/models.py`
- `backend/app/inventory/policy.py`
- `backend/app/inventory/repository.py`
- `backend/app/inventory/schemas.py`
- `backend/app/inventory/service.py`
- `backend/app/inventory/worker.py`
- `backend/app/api/inventory.py`
- `backend/app/main.py`
- `backend/app/purchases/models.py`
- `backend/app/purchases/schemas.py`
- `backend/worker/__main__.py`
- `database/migrations/env.py`
- `database/migrations/versions/0004_inventory.py`
- `tests/conftest.py`
- `tests/test_inventory_validation.py`
- `tests/test_inventory_integration.py`
- `tests/test_migrations.py`
- `DEVELOPMENT.md`
- `docs/README.md`
- `docs/api/api-contract.md`
- `docs/architecture/async-workers.md`
- `docs/data/database.md`
- `docs/domain/domain-model.md`
- `docs/workflows/inventory.md`
- `docs/workflows/receipt-ingestion.md`
- `docs/decisions/ADR-007-inventory.md`
- `docs/implementation/milestone-4-validation.md`

## Boundaries and deferrals

No legacy Streamlit or frontend changes. M3 extraction and receipt leases remain
unchanged. No M5 analytics or later feature is implemented. Automatic eligibility
requires explicit catalog configuration; absent a specified taxonomy, uncertain
lines are available for user enrollment. No expiry date is invented: M3 receipt.v1
does not supply expiry, and no estimation provider is added. Inventory UI,
automated estimation, deployed managed-task delivery, and multiple downstream
subscribers remain future work outside this subsystem milestone. The typed
evidence and task interfaces preserve those later integration boundaries.
