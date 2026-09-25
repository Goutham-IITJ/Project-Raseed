# Raseed V2 development

V2 lives in `apps/web`, `backend`, `database`, and `tests`. The root `main.py`,
legacy `requirements.txt`, `utilities`, `navigation_pages`, and `database_files`
remain the Streamlit prototype. Do not use its database, credentials, or storage
in V2. The authoritative architecture is in `docs/`.

## Requirements

- Python 3.10+ (CI uses 3.12), uv 0.9.5+, Node.js 20.9+ (CI uses 22), npm.
- Docker with Compose, running Linux containers.
- A Firebase project with Authentication → Google enabled and a registered web
  app. Add `localhost` to Authentication's authorized domains for local sign-in.

## Setup

From the repository root (PowerShell):

```powershell
Copy-Item .env.example .env
Copy-Item apps/web/.env.example apps/web/.env.local
uv sync --locked
npm.cmd --prefix apps/web ci
docker compose up -d --wait postgres
uv run alembic upgrade head
```

On macOS/Linux, use `cp` instead of `Copy-Item` and `npm` instead of `npm.cmd`.
Both lockfiles are checked in with the implementation; legacy dependencies are
not installed into the V2 environment.

Set the backend `FIREBASE_PROJECT_ID` in `.env`. Copy the Firebase Console web
configuration into `apps/web/.env.local`. Both sides must use the same project.
`NEXT_PUBLIC_*` Firebase values are public web configuration, not Admin secrets.

Configure Application Default Credentials for Firebase Admin, either using a
managed workload identity, a local ADC login with the necessary project access,
or `GOOGLE_APPLICATION_CREDENTIALS` pointing to a service-account file **outside
this repository**. Never paste Admin JSON or private keys into frontend variables.
The backend verifies revocation/disabled-user status, so the credential needs
Firebase Authentication user-read permission. `FIREBASE_AUTH_EMULATOR_HOST` is
deliberately rejected; there is no runtime authentication bypass.

Firebase reference: https://firebase.google.com/docs/auth/admin/verify-id-tokens

## Run

Run these in separate terminals from the repository root:

```powershell
uv run uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
uv run python -m backend.worker
npm.cmd --prefix apps/web run dev
```

Open http://localhost:3000 and select **Continue with Google**. The web SDK uses
browser-session persistence, obtains an ID token, and sends it in a bearer header
to `/api/v1/me`. First login provisions a user; repeated login loads the same UUID.
No access token is placed in a URL or custom local-storage entry. Sign-out clears
this browser session, not all tokens issued on every device.

API docs: http://localhost:8000/docs. `GET /health` is liveness only and can succeed
without Firebase or PostgreSQL. Authenticated endpoints fail closed when Firebase
is unavailable. Without Firebase configuration the web app shows an unavailable
sign-in state; it does not simulate a logged-in account.

The worker polls durable RECEIPT_UPLOADED outbox events in a separate process.
`uv run python -m backend.worker --once` dispatches one ready batch and exits.
PostgreSQL is the only Compose service required now.
Its development password is not suitable for deployment. It binds only loopback.
If port 5432 is unavailable, change `POSTGRES_PORT` in `.env` and use the same
port in `DATABASE_URL` and `TEST_DATABASE_URL`.

## Checks

```powershell
uv run --env-file .env pytest --cov=backend/app --cov-report=term-missing
uv run ruff check backend tests database
uv run ruff format --check backend tests database
uv run mypy backend
uv run alembic check
npm.cmd --prefix apps/web run lint
npm.cmd --prefix apps/web run typecheck
npm.cmd --prefix apps/web test
npm.cmd --prefix apps/web run build
```

The pytest command loads `TEST_DATABASE_URL` from the local `.env`, including
any custom PostgreSQL port. Alternatively, export it in your shell or CI.
Compose creates the separate `raseed_test` database on first volume initialization.
Integration tests truncate its user tables and exercise migration downgrade/upgrade; use only a
disposable database ending in `_test`. They refuse the application database and
skip explicitly when `TEST_DATABASE_URL` is missing. To run only credential-free
unit tests: `uv run pytest -m "not integration"`.

If using an existing Compose volume that predates the test database, create just
the missing database with `docker compose exec postgres createdb -U raseed raseed_test`.
Do not delete an existing volume merely to run tests. `docker compose down` stops
the infrastructure while retaining the volume.

## Boundaries

Routes delegate to services; services own transactions; repositories own SQL.
Provisioning alone accepts a `VerifiedIdentity`. All other user repositories
require a server-created `CurrentUser` and expose no target-user parameter.
Preferences are canonical key/value rows with a synchronized user-profile
projection. Defaults are INR, Asia/Kolkata, en-IN. Tokens, receipt contents, and
database parameters are not included in application error responses/logs.

Milestones 0–3 implement identity, canonical purchases, private receipt uploads,
and asynchronous extraction. Canonical purchase children, receipt success and
PURCHASE_CREATED commit atomically. Inventory and later integrations remain
outside this milestone. The existing frontend remains the identity foundation;
upload is available through the API and `/docs`.

## Receipt ingestion configuration

Local storage is the default: `.local/receipts` is ignored by Git and is not served
as web content. Restrict that directory to the service account (Windows uses
inherited directory ACLs; POSIX objects are created with mode 0600). API and worker
must use the same local storage path. For GCS, set STORAGE_PROVIDER=gcs and
GCS_BUCKET to an existing private bucket with uniform bucket access and public
access prevention enforced; configure ADC outside this repository.

Set GEMINI_API_KEY and GEMINI_MODEL in the ignored `.env` to enable the real
worker's Gemini adapter. Choose a model supporting multimodal input and structured
JSON output in your project. There is no hardcoded model default and no fake
provider selected by production environment configuration. Upload and local
storage work without Gemini configuration; a worker attempt reports a safe
configuration failure until credentials/model are configured.

The `.env.example` lists upload/page limits, extraction timeout, five-minute
lease, maximum attempts, retry delay, and worker polling settings. Receipt GET
responses include processing status, attempt count, purchase ID and safe reasons.
See [the workflow](docs/workflows/receipt-ingestion.md) for review/retry semantics.

After fixing a failure or extraction issue, an operator can requeue a stored
receipt while retaining its previous runs:

```powershell
uv run python -m backend.worker --retry <receipt-uuid> --once
```

No public retry/correction endpoint is exposed. Retryable failures schedule
another attempt with backoff; keep the polling worker running to process it.

## Deterministic local upload smoke check

This check exercises the authenticated upload endpoint with a real private local
storage provider, a fake extractor, and the disposable PostgreSQL database. It
checks 202 acceptance, outbox delivery, canonical persistence and PROCESSED status:

```powershell
uv run --env-file .env pytest tests/test_ingestion_integration.py -k upload_to_processed -v
uv run --env-file .env pytest tests/test_ingestion_integration.py -k real_http_smoke -v -s
```

Fake authentication/extraction are test injection only. Automated tests also
cover GCS and Gemini transport through mocks, with no live credentials.

## Optional live Gemini verification

Select a non-sensitive receipt that you explicitly want to send to Google. After
configuring GEMINI_API_KEY/GEMINI_MODEL locally, this command sends that file,
validates receipt.v1 and canonical financial rules, prints only a safe result,
and performs no database writes:

```powershell
uv run python -m backend.worker.verify --send-to-gemini --file C:/receipts/sample.png --timezone Asia/Kolkata
```

Live provider/account access is separate from deterministic validation. Do not
commit keys, receipt binaries, raw provider responses, or account credentials.
