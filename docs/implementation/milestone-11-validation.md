# M11 real provider integration checkpoint — 2026-10-02

Continued the clean working tree at
`7ff9f259bf0fe67651b663dcad003c152f3e9fd2`. Existing M10 interface, provider adapters,
domain semantics, migrations and legacy Streamlit files were preserved. The user
confirmed continuing with the configuration available in this environment.

## Actual verification and limits

**No external provider account was verified live.** Root/frontend environment
files contain placeholder Firebase values and empty AI configuration. Wallet
configuration and ADC are absent; storage is local. No key was fabricated, no
legacy credential reused and no mocked result was treated as Google/OpenAI
acceptance. The official OpenAI function-calling documentation was fetched to
review the existing Responses contract; this is documentation review only.

| Integration | Verification completed | Live check still required |
| --- | --- | --- |
| Firebase | Browser tests exercise Google sign-in/session transport; SDK-boundary tests enforce verified identity/revocation, invalid/expired/revoked/disabled tokens, provisioning and ownership. A real loopback API using current configuration fails closed with `authentication_unavailable`. | Interactive Google Sign-In, valid Firebase ID-token verification and account provisioning against the configured project. |
| Gemini | Actual adapter with mocked HTTP, original bytes, structured schema, validation, review decisions, bounded response reading/timeouts, retries and atomic canonical persistence. | Real receipt submission with a configured key/model and assessment of extracted fields. |
| Assistant | Actual Responses adapter with mocked HTTP through the complete application turn, approved tool dispatch, exact persisted citations, idempotency and safe failures. | Real model tool selection and final response using an authorized OpenAI key/model. |
| GCS | Private-bucket enforcement, immutable writes, authenticated file access, foreign-owner denial and safe credential/transport errors through deterministic mocks. Real private local-file storage and hash-checked retrieval pass. | Actual private GCS bucket upload/read, IAM/ADC acceptance and anonymous-access denial. |
| Wallet | Actual REST/IAM adapter with mocked transport through durable purchase synchronization and link issuance; separate tests cryptographically verify a temporary test-key signature. Ownership, canonical payloads, stable object IDs, retries and leases pass. | Real issuer/REST authorization, IAM signing and interactive acceptance/saving in Google Wallet. |

## Missing configuration in this environment

- Firebase: replace backend `FIREBASE_PROJECT_ID` and frontend
  `NEXT_PUBLIC_FIREBASE_API_KEY`, `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`,
  `NEXT_PUBLIC_FIREBASE_PROJECT_ID`, `NEXT_PUBLIC_FIREBASE_APP_ID`. Enable Google
  Authentication, register the web app and authorize the actual hostname. Backend
  and frontend projects must match.
- ADC: no `GOOGLE_APPLICATION_CREDENTIALS` setting or standard local ADC file was
  found. Supply managed identity or credentials outside this repository, including
  Firebase Authentication user-read permission. Bucket and issuer access are
  separate permissions; see the runbook.
- Extraction: `GEMINI_API_KEY` and `GEMINI_MODEL` are empty.
- Assistant: `OPENAI_API_KEY` and `ASSISTANT_MODEL` are empty.
- Storage: `STORAGE_PROVIDER=local`; `GCS_BUCKET` is empty. GCS verification needs
  `STORAGE_PROVIDER=gcs`, a real private bucket, ADC/project resolution, enforced
  public access prevention and uniform bucket-level access.
- Wallet: `WALLET_ISSUER_ID`, `WALLET_SERVICE_ACCOUNT_EMAIL`, `WALLET_ORIGINS` are
  absent from the active environment. Enable Wallet and IAM Credentials APIs,
  authorize the principals on the issuer and `iam.serviceAccounts.signJwt` on the
  signer, and configure test-user access/publishing approval.
- Local normal runtime: the existing `.env` addresses PostgreSQL on localhost
  port 55432, which is offline. Restore that service or configure a reachable
  **application** database and apply migrations. Validation reused the existing
  M10 PostgreSQL cluster on port 55439 with process-scoped overrides; `.env` was
  preserved and never redirected to the disposable test database.
- Deployment: set the actual HTTPS API base URL and explicit CORS/Wallet web
  origins; keep demo disabled. An interactive authorized Google account and a
  non-sensitive receipt selected for real provider processing are still needed.

Exact account permissions, setup, commands and ordered live checks are in
[provider-verification.md](provider-verification.md).

## End-to-end result

The new combined test uses real loopback HTTP, PostgreSQL and private local files,
the production Firebase/Gemini/OpenAI/Wallet adapters, and mocked SDK/HTTP provider
boundaries. It verifies:

`verified identity → upload → extraction → validated Purchase → Inventory →
Analytics → Assistant → Insights → Wallet synchronization/signing request`.

It checks repeated provisioning, duplicate-upload rejection, exact `11.000000 INR`
analytics/assistant evidence, explicit enrollment of a line with unknown catalog
eligibility, a rule-generated inventory expiry insight, stable Wallet object IDs,
same-key replay and cross-user denial. A second incomplete extraction enters
NEEDS_REVIEW without creating a purchase or scheduling blind retries.

The existing desktop/mobile browser suite verifies the UI flow with intercepted
Firebase/API transport. The separate demo suite uses real HTTP/PostgreSQL and
synthetic data. These layers do **not** constitute a single live Google Sign-In to
Google Wallet journey. Live end-to-end verification remains blocked by the settings
above. No receipt content, provider responses, tokens or signed save URLs are
committed as evidence.

## Changes

- Add safe `/ready` for database revision and local auth-configuration readiness;
  `/health` remains independent liveness. Neither contacts providers.
- Reject example Firebase values before SDK initialization; keep unavailable
  sign-in in the existing UI. No visual redesign.
- Validate exact CORS/Wallet origins and require HTTPS for production remote
  origins; retain loopback HTTP and existing demo restrictions.
- Hide input values in settings errors; bound database pool waits; make worker
  CLI database failures exit safely without SQL/credential tracebacks.
- Reject GCS emulator overrides and translate ADC/project/transport errors to
  existing safe storage failures. Bound Gemini response bytes and read duration.
- Add operational regression and combined journey tests, plus the setup/runbook.

The small operational API addition and safeguards are documented in
[ADR-015](../decisions/ADR-015-provider-verification.md). No dependency, schema,
service boundary, broker or deployment infrastructure was added.

## Validation

| Check | Result |
| --- | --- |
| Full backend pytest with disposable PostgreSQL and coverage | 991 passed, zero skipped, 98% coverage; 201.31 seconds |
| Final origin/error/readiness/worker regression suite | 44 passed |
| Frontend Vitest | 46 passed in 8 files |
| Frontend ESLint / TypeScript | Passed, zero lint warnings |
| Next.js production build | Passed, all product routes |
| Production build with demo enabled | Rejected as required |
| Standard Chromium desktop/mobile Playwright | 12 passed |
| Real HTTP/PostgreSQL demo Playwright | 6 passed |
| Ruff lint / formatting | Passed; 157 files formatted |
| mypy backend | Passed; 108 source files |
| Alembic upgrade / check | Passed; no schema drift |
| Real loopback API with current configuration | `/health` 200; `/ready` 503; missing bearer 401; unconfigured Firebase 503 |
| Actual worker `--once` with current offline application database | Safe database-unavailable message, exit 1, no traceback or connection details |
| Current tracked-file secret scan | No recognizable API/private keys or credential files; local env/password files ignored |
| Git whitespace / relative documentation links | Passed |

Validation used the existing Python environment directly (`python -m pytest`,
Ruff, mypy and Alembic), equivalent to the documented `uv run` checks. Only the
`raseed_validation_test` database was used for destructive backend tests. Demo
browser tests reused `raseed_redesign_demo`; the original `raseed_local_demo`
database was preserved. Browser assertions passed before Windows cleanup stalled;
stopping only the three test-owned server processes allowed both suites to exit
with status zero. No application process was stopped.

Local ignored reports: `.cache/m11-pytest.xml`, `.cache/m11-coverage.json` and
Playwright output under `apps/web/test-results`. Existing warnings concern
Starlette/httpx, Google's imminent Python 3.10 support end and Next.js's ignored
lockfile outside the repository. They do not represent live provider acceptance.

## Remaining limitations

The live provider matrix above remains unverified. Readiness checks local
configuration/schema, not ADC or external availability. A fresh catalog needs
explicit inventory enrollment through the existing API; the current UI has no
enrollment screen. Date-only/ambiguous receipts correctly require review, with
operator reprocessing and no correction UI. New accounts may have no insights
until sufficient real evidence exists. Wallet SYNCED and a signed URL do not
establish that a user saved the pass. Production deployment, workload IAM, worker
supervision and account publishing approval still need environment configuration.
