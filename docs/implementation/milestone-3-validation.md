# Milestone 3 validation checkpoint

Validated on 2026-09-25, building on Milestone 2 commit
`64d4c51cb6f94ec147e33106e184cac9d8edbdc3`.

## Result

Receipt ingestion and extraction are implemented within the modular monolith and
separate local worker. Private multipart uploads return 202; durable upload
events drive versioned Gemini extraction, application validation, normalization,
and atomic canonical persistence. The JSON metadata API remains compatible.
See ADR-006 and the receipt-ingestion workflow for the complete contract.

| Check | Result |
| --- | --- |
| Complete Python suite, PostgreSQL enabled | 269 passed, zero skipped |
| PostgreSQL integration tests within that suite | 91 passed |
| Backend coverage | 96% |
| Ruff check | Passed |
| Ruff format --check | 53 files formatted |
| mypy backend | Passed, 38 source files |
| Development Alembic upgrade/current/check | 0003_receipt_ingestion, no schema drift |
| Migration round trips and M1/M2 data preservation | Passed in disposable test database |
| Real loopback HTTP upload smoke | 202 UPLOADED → 200 PROCESSED and canonical purchase |
| Existing frontend tests | 4 passed |

The local PostgreSQL server uses port 55432; integration tests used `raseed_test`,
separate from the development `raseed` database. The HTTP smoke test used private
LocalStorageProvider files and a deterministic injected extractor. No live model
or cloud credentials were required. Test output includes the existing
Starlette/httpx deprecation warning and Google's Python 3.10 support warning.

The suite covers supported formats, invalid uploads, ownership, duplicate and
concurrent uploads, private storage, schema/financial validation, missing values,
provider failures, review states, bounded retries, explicit retry, stale-worker
fencing, catalog reuse, and rollback after upload/canonical event writes.

## Live verification and intentional deferrals

Gemini request construction, structured-output options, response handling and
error classification are verified through mocked HTTP. The responseJsonSchema
option was checked against Google's official generateContent documentation.
GCS private-bucket checks and blob operations are verified through mocks.
Live Gemini/GCS account access was not exercised. DEVELOPMENT.md includes an
explicit `backend.worker.verify --send-to-gemini` command that performs no
database writes and does not print extracted receipt contents.

Cloud Tasks/HTTP deployment and service authentication, a receipt frontend,
manual correction UI, automatic orphan cleanup, and downstream feature consumers
are deferred. Date-only receipts enter review rather than inventing a timestamp.
No inventory or Milestone 4 work is included. Legacy Streamlit files are unchanged.

## Files changed

Configuration and dependencies:

- `.env.example`
- `.gitignore`
- `pyproject.toml`
- `uv.lock`

Application and worker:

- `backend/app/api/purchases.py`
- `backend/app/config.py`
- `backend/app/main.py`
- `backend/app/purchases/models.py`
- `backend/app/purchases/repositories.py`
- `backend/app/purchases/schemas.py`
- `backend/app/ingestion/__init__.py`
- `backend/app/ingestion/errors.py`
- `backend/app/ingestion/extractor.py`
- `backend/app/ingestion/factory.py`
- `backend/app/ingestion/gemini.py`
- `backend/app/ingestion/lifecycle.py`
- `backend/app/ingestion/normalization.py`
- `backend/app/ingestion/repository.py`
- `backend/app/ingestion/schema.py`
- `backend/app/ingestion/service.py`
- `backend/app/ingestion/storage.py`
- `backend/app/ingestion/upload.py`
- `backend/app/ingestion/validation.py`
- `backend/worker/__main__.py`
- `backend/worker/verify.py`
- `database/migrations/versions/0003_receipt_ingestion.py`

Tests:

- `tests/ingestion_fixtures.py`
- `tests/test_extraction.py`
- `tests/test_ingestion_integration.py`
- `tests/test_migrations.py`
- `tests/test_receipt_storage.py`

Documentation:

- `DEVELOPMENT.md`
- `docs/README.md`
- `docs/api/api-contract.md`
- `docs/architecture/async-workers.md`
- `docs/data/database.md`
- `docs/decisions/ADR-006-receipt-ingestion.md`
- `docs/workflows/receipt-ingestion.md`
- `docs/implementation/milestone-3-validation.md`

Architecture decision: [ADR-006-receipt-ingestion.md](../decisions/ADR-006-receipt-ingestion.md).
