# Local demo mode

The completed M10 UI can be browsed without Firebase credentials using an
explicit development-only account. Every displayed amount comes from synthetic
records in the existing PostgreSQL domain model. A persistent banner labels the
data. This is not a production sign-in option. See [ADR-014](../decisions/ADR-014-local-demo.md).

## Setup (PowerShell, repository root)

Use the existing Python environment and frontend dependencies (`uv sync --locked`
and `npm.cmd --prefix apps/web ci` if needed). Keep your normal `.env` unchanged.
Start the existing development PostgreSQL service and create a separate database:

```powershell
docker compose up -d --wait postgres
docker compose exec postgres createdb -U raseed raseed_demo
```

Run `createdb` only once; an existing database should be reused, not removed.
For native PostgreSQL use its `createdb -h 127.0.0.1 -p <port> -U <user> raseed_demo`
instead. The following URL assumes the repository's default Compose credentials
and port; use your local port/password if different. The database must end `_demo`.
Use UTC as the PostgreSQL session default, as in the Compose setup. On a native
installation configured with a local timezone, run
`ALTER DATABASE raseed_demo SET timezone TO 'UTC';` once via `psql`.

```powershell
$env:APP_ENV = "development"
$env:LOCAL_DEMO = "true"
$env:DATABASE_URL = "postgresql+psycopg://raseed:raseed_local@127.0.0.1:5432/raseed_demo"
$env:CORS_ORIGINS = '["http://localhost:3000","http://127.0.0.1:3000"]'
$env:STORAGE_PROVIDER = "local"
$env:LOCAL_STORAGE_PATH = ".local/demo-receipts"
uv run alembic upgrade head
uv run python -m backend.demo seed
uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

In a second PowerShell terminal, from the repository root:

```powershell
$env:NEXT_PUBLIC_LOCAL_DEMO = "true"
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000"
npm.cmd --prefix apps/web run dev -- --hostname 127.0.0.1 --port 3000
```

Open **http://localhost:3000**. The app loads the fixed `Alex Demo` account
(`demo@example.test`, external identity `raseed-local-demo-v1`) through the real
API. No Google login or Firebase network request is made. Sign-out stays effective
in that browser tab until **Enter local demo** is selected. Restarting a terminal
clears these process-scoped environment overrides. No secrets belong in Git.

## Seed behavior

`python -m backend.demo seed` creates the following once, in one transaction:

- 24 purchases across three calendar periods, INR and USD, four merchants,
  four categories, six products and 29 lines, including unknown prices and all
  four payment statuses. Payments and totals pass normal domain validation.
- Four visibly synthetic PNG receipts: one original linked to a processed
  purchase, plus uploaded, needs-review and failed examples.
- Six inventory lots with consumption history, a depleted item, unknown expiry,
  due/past-due dates, and an explicitly inferred expiry with confidence.
- Four inventory insights computed by existing rules, with active, read and
  dismissed examples and full source evidence.
- Three explicitly synthetic memories and three sample conversations: two
  completed replies grounded in real purchase-tool results, plus one failed reply.
- Five illustrative Wallet states: pending, syncing, retry, failed and synced.
  Their provider references are synthetic; nothing was issued to Google.

The fixed external identity goes through normal user provisioning. Every owned
record belongs to that user; catalog records remain shared under the existing
schema and are reachable through the demo user's purchases. No parallel tables,
new migration or frontend financial fixtures are used.

Repeating the seed reports `already seeded` and preserves IDs, preferences,
inventory edits and historical dates. Concurrent runs cannot duplicate the seed.
Failed runs roll back records and remove only the new receipt files from that
attempt. Dates use the first seed's Asia/Kolkata date. For reproducible fixtures,
pass `--as-of YYYY-MM-DD` on the first run. As time passes, expiry/period displays
change normally. Use another dedicated `_demo` database for a fresh dated sample;
the command deliberately does not reset or delete existing data.

## Limits and production guards

Demo is off by default. The backend refuses demo with production/test APP_ENV,
remote databases, non-demo database names, GCS, nonlocal CORS or recognized hosted
runtime markers. Every request must also have a loopback peer and Host, and an
allowed Origin when present. It accepts only one dedicated demo credential and
never a client-selected identity. Normal mode still uses the original Firebase
verification, including revocation checks.

Demo supports reading records, inventory updates, insight controls, preferences
and local receipt uploads. Uploads remain queued. Live assistant/market/Wallet
actions and the external worker are disabled; sample transcripts and Wallet
states are illustrative. Memory records are available through the existing API;
M10 does not have a memory-management screen. No live provider credentials are needed.

Next.js rejects demo mode during production build and start, and production
client code cannot select demo identity. To run the normal production checks:

```powershell
$env:NEXT_PUBLIC_LOCAL_DEMO = "false"
npm.cmd --prefix apps/web run build
```

For normal backend operation, unset LOCAL_DEMO or set it false and restore your
usual DATABASE_URL. Do not point a normal external worker at the demo database.

## Verification commands

The normal backend suite needs the existing separate `TEST_DATABASE_URL` ending
`_test`; never run destructive integration tests against the demo database.

```powershell
uv run pytest tests/test_local_demo.py tests/test_identity_integration.py
uv run ruff check backend tests database
uv run ruff format --check backend tests database
uv run mypy backend
npm.cmd --prefix apps/web test
npm.cmd --prefix apps/web run lint
npm.cmd --prefix apps/web run typecheck
npm.cmd --prefix apps/web run build
npm.cmd --prefix apps/web run test:e2e
```

The additional demo browser suite uses real HTTP and PostgreSQL, without Firebase
or API interception. Give it a dedicated, already-created `_demo` database:

```powershell
$env:DEMO_E2E_DATABASE_URL = "postgresql+psycopg://raseed:raseed_local@127.0.0.1:5432/raseed_browser_demo"
npm.cmd --prefix apps/web run test:demo
```

It applies existing migrations, idempotently seeds that database, and starts its
own API/web servers on ports 8101/3101. Receipt files live in
`.local/demo-e2e-receipts`. Reuse the same storage directory with an already-seeded
database. On Windows, Playwright needs process permissions to stop its servers.
On macOS/Linux, use `npm` and `export NAME=value` instead of `npm.cmd` and `$env:`.
