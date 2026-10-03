# Raseed V2 development

To browse the completed UI without Firebase credentials, follow the
[local demo setup and seed commands](docs/implementation/local-demo.md).
Demo is development-only, uses a separate database and labels all synthetic data.

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

For local or non-Google development, store these backend settings in the ignored
root `.env` (replace the examples with your project and an absolute path):

```dotenv
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_ADMIN_CREDENTIALS_PATH="C:/private/firebase-service-account.json"
```

Keep the actual service-account JSON **outside this repository**. On macOS/Linux,
use an absolute path such as `/home/you/.config/raseed/firebase-service-account.json`.
Quote paths containing spaces; forward slashes work on Windows. The backend loads
the root `.env` automatically at startup, independently of the working directory;
no shell exports or `uv run --env-file` are needed for these settings. Restart the
backend after changing them. Process environment values override `.env` values.

The configured path takes precedence for Firebase Admin only. Leave
`FIREBASE_ADMIN_CREDENTIALS_PATH` unset or blank in deployed Google environments
to preserve Application Default Credentials (ADC), including managed workload
identity. Local ADC login and an existing shell `GOOGLE_APPLICATION_CREDENTIALS`
also continue to work when the explicit path is absent. A
`GOOGLE_APPLICATION_CREDENTIALS` entry in `.env` alone is not exported to the Google
SDK; use the explicit Firebase setting above for persistent local setup. GCS and
Wallet retain their separate ADC configuration.

Admin initialization remains lazy: startup makes no Google request. An unreadable
or invalid configured file causes authenticated requests to fail with a safe
`authentication_unavailable` (503), without falling back to another identity.
Never commit `.env` or service-account JSON, or paste Admin JSON/private keys into
source code or frontend variables.
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

`GET /ready` separately checks local Firebase project configuration and the
database migration revision, returning a safe 503 when unavailable. It makes no
provider call and does not attest to ADC, sign-in, worker or provider health.
Example Firebase placeholders are treated as unconfigured by the browser and API.
For real provider setup, exact manual verification steps and the current M11
limitations, see [the provider verification runbook](docs/implementation/provider-verification.md)
and [M11 results](docs/implementation/milestone-11-validation.md).

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

Milestones 0–7 implement identity, canonical purchases, private receipt uploads,
and asynchronous extraction. Canonical purchase children, receipt success and
PURCHASE_CREATED commit atomically. Inventory consumes that event and exposes
owned stock/lot/history and correction APIs. Deterministic analytics reads canonical
purchases directly and exposes filtered history, summaries, category/merchant
breakdowns, and comparisons. The assistant persists owned conversations and uses
approved financial and inventory read tools. Later integrations remain deferred.
Explicit long-term memory, relevant assistant recall, and asynchronous canonical
spending/inventory insights are also implemented. Their APIs are available in `/docs`.
The existing frontend remains the identity foundation;
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

## Inventory worker and local verification

`uv run python -m backend.worker` now polls both receipt and purchase events.
Inventory has no provider/credential dependency. A purchase with explicitly
eligible catalog product/category, known quantity and unit creates inventory;
uncertain lines require user confirmation through POST /api/v1/inventory/lots.
Catalog flags are optional typed internal catalog inputs, not model-supplied or
public writes. No taxonomy is automatically seeded. See the inventory workflow
and API contract for stock commands and expiry semantics.

Inventory delivery failure is recorded on the PURCHASE_CREATED outbox row:
attempt_count, failure_code, failed_at. Three attempts use 5/10-second backoff.
After diagnosing/fixing the cause, an operator may requeue an exhausted purchase:

```powershell
uv run python -m backend.worker --retry-inventory <purchase-uuid> --once
```

The following checks use the disposable test database, fake authentication/model
and real private local storage. The HTTP smoke uploads a receipt, processes M3,
consumes PURCHASE_CREATED, reads inventory and records a consumption correction:

```powershell
uv run --env-file .env pytest tests/test_inventory_validation.py tests/test_inventory_integration.py -v
uv run --env-file .env pytest tests/test_inventory_integration.py -k local_http -v -s
```

The smoke fixture configures an eligible test category explicitly. It does not
seed the development catalog or contact Gemini. Receipt expiry remains UNKNOWN
until explicit evidence exists; no expiry guesses or automatic depletion occur.

## Financial analytics verification

The analytics endpoints are available through `/docs` and require the same bearer
authentication as purchase reads. No worker, model key, or cloud account is needed.
Omitting currency returns separate groups for each currency; omitting a period
defaults analytics to the owner's current local calendar month. Purchase history
still defaults to all-time. Dates use an inclusive start and exclusive end.

```powershell
uv run --env-file .env pytest tests/test_analytics_validation.py tests/test_analytics_integration.py -v
uv run --env-file .env pytest tests/test_analytics_integration.py -k local_http -v -s
uv run alembic upgrade head
uv run alembic check
```

The HTTP check uses canonical synthetic purchases in the disposable `raseed_test`
database, test-only authentication, and a real loopback HTTP server. It exercises
all four analytics endpoints and filtered purchase history. Tests also cover
mixed currencies, unknown line totals, split payments, DST boundaries, snapshot
consistency, ownership, and index preservation across migration round trips.
See the API contract and ADR-008 for precise metric/rounding semantics. Budget
persistence and recurring-pattern inference remain deferred.

## Assistant configuration and verification

The four assistant routes are available in `/docs` under
`/api/v1/assistant/conversations`. Conversation creation and history need no model
credentials. Set `OPENAI_API_KEY` and `ASSISTANT_MODEL` in the ignored `.env` to
enable the OpenAI Responses adapter. Choose a model available to your account that
supports function calling and strict structured output. There is no hardcoded
model default or production fake-provider switch. Missing configuration produces
a safe, persisted failure when a message is submitted; startup makes no AI call.
Receipt extraction continues to use its independent Gemini configuration.

Each message POST requires `content` and a UUID `idempotency_key`. Reuse the key
when recovering a lost HTTP response. A failed key retains its failure; explicitly
retry with a new key. Concurrent new messages in one conversation return 409;
identical requests still running return 202. Use GET messages to read persisted
status, response evidence, and tool audit records. The default loop allows six
model rounds, eight tool invocations and two attempts per provider request, with
a twenty-second request timeout and two-minute turn limit. `.env.example` lists
the bounded configuration values. Expired turns are closed on the next POST.

The adapter sends only the owned conversation context and approved tool results
needed for that turn. It uses `store:false`; encrypted provider continuation stays
transient. No raw provider response/reasoning is stored. Client content, catalog
text and tool results are treated as untrusted input. No SQL, owner selection,
inventory writes, budgets, memory, or proactive insights are exposed as tools.

Credential-free deterministic tests and a real loopback HTTP/PostgreSQL smoke:

```powershell
uv run --env-file .env pytest tests/test_assistant_validation.py tests/test_assistant_provider.py tests/test_assistant_integration.py -v
uv run --env-file .env pytest tests/test_assistant_integration.py -k local_http -v -s
uv run alembic upgrade head
uv run alembic check
```

These tests inject fake authentication/model boundaries only in test-created apps;
PostgreSQL and HTTP are real. They require the separate disposable test database
described above and never call a live model. Tests cover exact analytics and
inventory results, owner isolation, retries, duplicate submissions/calls, stale
workers, and grounded response persistence. The OpenAI transport is separately
mocked. See ADR-009 and the assistant API contract for exact lifecycle semantics.

## Memory and insights configuration and verification

M7 requires no additional credentials or services. Apply migration
`0007_memory_insights` and keep `uv run python -m backend.worker` running. The
worker now dispatches receipt, inventory and insight jobs, and schedules daily
financial and per-lot evaluations using each owner's local calendar. `--once`
schedules/dispatches a bounded batch; keep polling to drain larger backlogs.

Memory controls: POST/GET `/api/v1/memories`, GET/PATCH/DELETE
`/api/v1/memories/{id}`. These explicitly save/update/delete typed user statements;
they never harvest transcripts. PATCH replaces the statement and optional fields
using `expected_version`; DELETE requires `?expected_version=...`. Search and
assistant recall exclude expired/deleted memories. Topic relevance supports food,
spending, inventory, shopping and goals alongside lexical matching.

Insight controls: GET `/api/v1/insights`, GET/PATCH `/api/v1/insights/{id}`. PATCH
marks READ or DISMISSED with an expected version. Generation runs only in the
worker, using existing analytics/inventory services and deterministic explanation
templates. Default reads return active/read unexpired observations. The assistant
can read their structured sources; its original tools still supply current data.
No live OpenAI/Gemini call is needed for these subsystems or their tests.

Insight retry state is independent of inventory delivery on the outbox row. After
diagnosing an exhausted/permanent failure, requeue its event ID explicitly:

```powershell
uv run python -m backend.worker --retry-insight <outbox-event-uuid> --once
```

Verification uses the same disposable PostgreSQL database as the existing suite:

```powershell
uv run --env-file .env pytest tests/test_memory_validation.py tests/test_memory_integration.py tests/test_insights_integration.py tests/test_memory_insights_migration.py tests/test_memory_insights_http.py -v
uv run --env-file .env pytest tests/test_memory_insights_http.py -v -s
uv run --env-file .env pytest
uv run ruff check backend tests database
uv run ruff format --check backend tests database
uv run mypy backend
uv run alembic upgrade head
uv run alembic check
```

The HTTP smoke verifies explicit memory creation/deletion, relevant assistant
recall, exact inventory evidence, insight dismissal and owner isolation against
real PostgreSQL. Authentication and model boundaries are test injections only.
Rule thresholds, evidence limits, snapshots and deferrals are recorded in ADR-010
and `docs/workflows/memory-insights.md`.

## Google Wallet configuration and verification

M8 uses the existing PostgreSQL and separate worker. Apply `uv run alembic upgrade
head`, then run `uv run python -m backend.worker`. PURCHASE_CREATED events,
including existing purchases, become durable WalletPass jobs in batches of twenty.
The API can queue/read a pass without Google credentials. Unconfigured worker
attempts fail visibly with wallet_configuration and can be requeued after setup.

Configure WALLET_ISSUER_ID, WALLET_SERVICE_ACCOUNT_EMAIL, WALLET_ORIGINS (a JSON
array of explicit HTTP(S) web origins), and optionally WALLET_REQUEST_TIMEOUT_SECONDS
(default 15). Enable the Google Wallet API and IAM Service Account Credentials API.
Use managed Application Default Credentials with Wallet issuer access; register the
configured signing service account with the same Wallet issuer. The ADC principal
needs iam.serviceAccounts.signJwt on that signer (for example the appropriately
scoped Service Account Token Creator role). This also applies when the caller and
signer are the same service account. Production publishing/issuer approval and test
user access are controlled by Google. No account credentials are committed or needed
by automated tests. The application makes no Google request at startup.

POST `/api/v1/wallet/passes` with purchase_id queues one owned Generic pass. GET
collection/detail reads persisted status. POST `/{id}/sync` with `{}` requeues a
SYNCED/FAILED pass; pending jobs retain backoff. POST `/{id}/add-to-wallet` with `{}`
returns a signed Google save URL only after SYNCED. URLs are bearer capabilities
and should be used transiently. No Google user account is linked or saving tracked.
The API contract and ADR-011 describe fields, safe errors and lifecycle precisely.

Transient failures receive three attempts with 5/10-second backoff and bounded
Retry-After. Permanent/exhausted jobs stay FAILED. After fixing the cause, use the
owned sync endpoint or `uv run python -m backend.worker --retry-wallet <pass UUID>
--once`. The same issuer/object IDs are retained across retries and reconstruction.
Worker crashes recover after a five-minute lease; external calls hold no DB locks.

Tests use fake providers and mocked Google REST/IAM signing with real PostgreSQL.
With TEST_DATABASE_URL set to the separate disposable database, run:

```powershell
uv run pytest
uv run ruff check backend tests database
uv run ruff format --check backend tests database
uv run mypy backend
uv run alembic upgrade head
uv run alembic check
```

On uv versions that strip embedded JSON quotes with `--env-file`, export only
TEST_DATABASE_URL from `.env` for tests; application settings already load `.env`
through pydantic-settings. Live Wallet credential/issuer validation is separate
from the automated suite. Legacy Streamlit and frontend code are unchanged.

## Market intelligence configuration and verification

M9 adds MarketSearch requests and external MarketPriceObservation records. Apply
`uv run alembic upgrade head` and run the existing `uv run python -m backend.worker`.
The API and assistant queue lookups; the separate worker performs external I/O.
Searches, observations, comparisons and retries use `/api/v1/market` (see `/docs`).
The assistant adds search_market_prices/get_market_search with its existing audit
and grounding. Pending requests are read later; no automatic assistant reply or
notification is introduced.

The first adapter is eBay Browse. Configure MARKET_EBAY_TOKEN with an application
OAuth token for the Browse API and MARKET_EBAY_MARKETPLACE with EBAY_US, EBAY_GB,
EBAY_DE or EBAY_AU. The requested destination must match that marketplace's country.
Keep the token in the ignored environment/secret manager and rotate it according
to its lifetime; invalid/expired credentials fail visibly and can be retried after
replacement. MARKET_REQUEST_TIMEOUT_SECONDS defaults to 10 (maximum 20). No token
is needed for startup or tests, and no live provider request was used in validation.
Other regions, including Indian retail coverage, need another provider adapter;
Raseed never converts currencies to make incompatible offers appear comparable.

Canonical Product metadata may carry `identity_source: OBSERVED`, a checksum-valid
`gtin`, `mpn`, `variant` and `pack` with explicit quantity/unit/count. Existing receipt
ingestion supplies observed GTIN where available; absent pack data stays unknown.
M9 does not enrich catalog records or guess pack sizes from receipt/listing titles.
Only complete compatible identity/pack/pricing evidence supports lower displayed
price. The eBay adapter uses explicit listing aspects and often returns observations
without enough evidence for comparison. Shipping/tax and checkout savings remain
separate from this display-price comparison.
Multi-item lots leave pack composition unknown; the adapter does not assume that
listing aspects describe the full lot.

External observations retain source URL, seller/destination context, observed/fetched
time, expiry and matching confidence. A fifteen-minute freshness limit, bounded
cache, three attempts with backoff, leases and explicit failed-request retry keep
external failures independent of purchases. Old observations remain readable but
cannot support a fresh comparison. Full contracts are in ADR-012 and the API docs.

With TEST_DATABASE_URL set to the separate disposable PostgreSQL database:

```powershell
uv run pytest
uv run ruff check backend tests database
uv run ruff format --check backend tests database
uv run mypy backend
uv run alembic upgrade head
uv run alembic check
```

The deterministic tests cover matching uncertainty, pack/unit/currency differences,
provenance, stale evidence, ownership, malformed responses, retry/crash recovery,
asynchronous assistant invocation and preservation of canonical/M8 data. No UI,
Wallet behavior, notification or currency-conversion feature is included.


## Product interface (M10)

The Next.js app in `apps/web` now provides Overview, Purchases and purchase
Details, Inventory and lot activity, Insights and evidence, Assistant conversation
history, Google Wallet passes, Settings, and a persistent Add Receipt dialog.
It uses the existing Firebase Google sign-in and backend APIs. Copy the frontend
`.env.example` to the ignored `.env.local` and configure your Firebase public web
metadata and API origin. Run the backend and existing receipt/inventory/insight/
Wallet worker as described above; uploads and pass preparation complete there.

```powershell
cd apps/web
npm.cmd ci
npm.cmd run dev
```

The UI keeps currencies separate, formats server decimal strings without floating
point conversion, and labels unknown/estimated/external evidence. Inventory
updates append versioned, idempotent events. Receipt and assistant polling stop
after forty three-second refreshes and retain manual refresh. Needs-review
receipts explain the current support path; no correction endpoint is invented.
Settings save currency, locale and timezone, then reload the account. Firebase
session persistence clears the browser session on sign-out.

Validation:

```powershell
npm.cmd test
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
npm.cmd exec playwright install chromium
npm.cmd run test:e2e
```

Use `npm` instead of `npm.cmd` on macOS/Linux. Playwright starts a separate local
Next dev server on port 3100 with test-only public configuration, seeds Firebase
session persistence in an isolated browser context, and intercepts Firebase/API
transports. It never contacts production or adds a production authentication
bypass. Desktop and mobile tests cover navigation/focus, capture, private receipt
viewing, inventory changes, insight dismissal, Wallet retry, assistant evidence,
preferences, sign-out and error/empty states at 320px. Browser traces/screenshots
are ignored locally and uploaded by CI on failure. Backend integration tests
separately exercise real PostgreSQL ownership, literal purchase search and private
file reads. Live Google sign-in/provider credentials remain environment setup.
