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

The worker skeleton can be checked with `uv run python -m backend.worker`; it exits
without starting any jobs. PostgreSQL is the only Compose service required now.
Its development password is not suitable for deployment. It binds only loopback.
If port 5432 is unavailable, change `POSTGRES_PORT` in `.env` and use the same
port in `DATABASE_URL` and `TEST_DATABASE_URL`.

## Checks

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://raseed:raseed_local@localhost:5432/raseed_test'
uv run pytest --cov=backend/app --cov-report=term-missing
uv run ruff check backend tests database
uv run ruff format --check backend tests database
uv run mypy backend
uv run alembic check
npm.cmd --prefix apps/web run lint
npm.cmd --prefix apps/web run typecheck
npm.cmd --prefix apps/web test
npm.cmd --prefix apps/web run build
```

For a POSIX shell use `export TEST_DATABASE_URL='...'`. Compose creates the
separate `raseed_test` database on first volume initialization. Integration tests
truncate its user tables and exercise migration downgrade/upgrade; use only a
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

Only identity and preferences are implemented. Receipt/purchase foundations are
Milestone 2, ingestion/extraction Milestone 3, inventory Milestone 4. Budget
persistence remains undecided. No outbox events are defined for Milestone 1, and
the worker is intentionally inactive. Later event-producing services must commit
canonical state and its corresponding outbox event in one PostgreSQL transaction.
