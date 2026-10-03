# M11 provider setup and end-to-end verification

V2 uses Firebase Google Sign-In, Gemini receipt extraction, OpenAI Responses for
the assistant, private local/GCS receipt storage, and Google Wallet REST plus IAM
signing. These existing adapters are independent: a Gemini key does not configure
the assistant. Never reuse legacy Streamlit keys, storage or database records.
Automated tests inject authentication and provider boundaries; passing them is
not live provider verification.

## Configuration

Keep secrets in the ignored root `.env`, external ADC credentials or managed
workload identity. The frontend `.env.local` contains only public Firebase web
metadata and the API origin. Rebuild the frontend after changing `NEXT_PUBLIC_*`
values; Next.js embeds them at build time. Never place Admin JSON, AI keys, ADC
tokens, signing keys or database URLs in `NEXT_PUBLIC_*` variables.

| Integration | Required configuration and account setup |
| --- | --- |
| Firebase | Backend `FIREBASE_PROJECT_ID` and optional `FIREBASE_ADMIN_CREDENTIALS_PATH` in the ignored root `.env`, loaded automatically at startup. For local/non-Google development, use an absolute path to a service-account JSON outside the repository; leave blank for ADC. The explicit path takes precedence for Firebase Admin only. The credential needs Authentication user-read access for revocation/disabled-user checks. Frontend `NEXT_PUBLIC_FIREBASE_API_KEY`, `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`, `NEXT_PUBLIC_FIREBASE_PROJECT_ID`, `NEXT_PUBLIC_FIREBASE_APP_ID`; both project IDs must match. Enable Google in Firebase Authentication, register the web app and authorize the actual web hostname, including localhost for development. |
| Google ADC | Managed identity, local ADC login or `GOOGLE_APPLICATION_CREDENTIALS` in the process environment pointing outside the repository. Used by Firebase when its explicit Admin path is absent, and independently by GCS/Wallet. An ADC path in `.env` alone is not exported to the SDK. GCS additionally needs a resolvable Google project (`GOOGLE_CLOUD_PROJECT` if ADC does not provide one). A credential file's presence alone does not prove permissions. |
| Gemini extraction | `GEMINI_API_KEY` and `GEMINI_MODEL`, with account access/quota for multimodal `generateContent` and JSON Schema output. Model IDs stay explicit configuration. |
| Assistant | `OPENAI_API_KEY` and `ASSISTANT_MODEL`, with account access/quota for Responses function calling and strict structured output. The adapter uses `store:false`; application services validate all tool arguments and render cited values. |
| GCS | `STORAGE_PROVIDER=gcs`, `GCS_BUCKET` naming an existing private bucket; uniform bucket-level access and **enforced** public access prevention. ADC needs `storage.buckets.get` and object create/get/delete access to the receipt namespace. API and worker must share the same bucket/configuration. No browser-to-GCS upload or public object URL is used. |
| Wallet | `WALLET_ISSUER_ID`, `WALLET_SERVICE_ACCOUNT_EMAIL`, `WALLET_ORIGINS` (JSON array). Enable Google Wallet API and IAM Service Account Credentials API. Grant issuer access to the REST principal and signing service account; ADC needs `iam.serviceAccounts.signJwt` on the signer. Configure Google's test users or publishing approval. The API does not create an issuer or grant roles. |
| API and worker | Reachable PostgreSQL `DATABASE_URL`, current migrations, shared receipt storage, `LOCAL_DEMO=false`; run API and `python -m backend.worker` separately. A disposable `_test` database is only for automated validation. |
| Origins | `NEXT_PUBLIC_API_BASE_URL` must address the API. `CORS_ORIGINS` must list the exact browser origins; `WALLET_ORIGINS` must include those used for saving. Paths, credentials, wildcard hosts, malformed ports and URL suffixes are rejected. Production remote origins require HTTPS; loopback HTTP is supported locally. |

`FIREBASE_AUTH_EMULATOR_HOST` and `STORAGE_EMULATOR_HOST` must be unset for real
adapters. Demo requires its existing development/loopback/isolated-database gates
and disables live actions and the external worker. A production deployment needs
HTTPS termination, real database credentials and appropriate private-storage IAM;
the example Compose database password is for local development only.

## Local operational checks

Run `uv run alembic upgrade head` and `uv run alembic check` against the intended
application database. `GET /health` should return 200 even if dependencies are
down. `GET /ready` should return 200 only when local project configuration and the
database revision are ready. Missing configuration, a database outage or an older
schema returns 503 with no connection details. Neither endpoint proves external
credentials or contacts Google/OpenAI. Readiness is separate from worker health.

From the actual frontend origin, verify an OPTIONS preflight permits POST with
Authorization and Content-Type. An unlisted Origin must receive no allow-origin
header. Bearer authentication remains required for every product route regardless
of CORS. Deployment ingress should preserve no-store responses and avoid logging
Authorization headers, multipart bodies, receipt content or signed Wallet URLs.

Run `uv run python -m backend.worker --once` to dispatch one ready batch. Keep the
polling worker running for delayed retries and multiple batches. API and worker
must use the same database and storage. Worker database failures exit nonzero in
`--once` mode with safe text; polling retains durable pending work. Safe job codes,
attempt counts and timestamps are available in existing receipt/Wallet views.

## Live journey (requires credentials and an interactive Google user)

1. Start the normal API, worker and frontend with demo disabled. Use **Continue
   with Google** in the browser. Confirm `/api/v1/me` succeeds with a Firebase ID
   token, repeated requests retain the same internal UUID and sign-out clears
   the browser session. Use a second authorized account to check ownership.
   Do not paste ID tokens into documentation, terminal history or issue reports.
2. Select **Add Receipt** and upload a non-sensitive receipt authorized for sending
   to Google. Prefer a clear receipt with an observed date **and time**, merchant,
   currency and total. Record only safe status/IDs. Upload returns 202, then the
   separate worker invokes Gemini and validates `receipt.v1` and financial rules.
   Confirm PROCESSED links to exactly one purchase. Duplicate bytes for the same
   owner return 409. Missing time, low confidence or conflicting totals should
   produce NEEDS_REVIEW with no purchase; that is a correct outcome, not a pass
   on extraction quality. Do not invent facts to get a success result.
3. For a standalone extraction probe, use the existing command:

   ```powershell
   uv run python -m backend.worker.verify --send-to-gemini --file C:/receipts/sample.png --timezone Asia/Kolkata
   ```

   It sends the selected file to Gemini, performs no database writes, and prints
   only validation status. A valid result is a live extraction check, not a full
   application journey.
4. With GCS selected, confirm upload and authorized original-file retrieval return
   matching bytes through `/api/v1/receipts/{id}/file`. Verify a signed-out/foreign
   user gets 401/404 and an anonymous GCS object read is denied. Keep object names
   private. The adapter rechecks bucket privacy before each operation and never
   sets public ACLs. Local storage success is not GCS verification.
5. Compare the purchase's exact observed values with the source. Inventory only
   auto-enrolls lines with existing eligible catalog metadata, quantity and unit.
   A fresh unseeded catalog normally needs explicit user confirmation through
   `POST /api/v1/inventory/lots`; M10 has no enrollment screen. Use the authenticated
   API docs with a line ID, idempotency key, confirmed quantity/unit and reason.
   Existing lot updates always append inventory events; never seed eligibility
   or infer an expiry just to complete a live demonstration.
6. Check Analytics for a period that includes the purchase. Confirm exact totals,
   currency separation and ownership. Ask the Assistant about that period; verify
   COMPLETED, a real provider/model attempt, successful approved tool executions
   and exact cited values. Replay the same message idempotency key to confirm
   no second provider turn. Safe model failure is not a real-response success.
7. Read Insights after worker dispatch. They are deterministic and need adequate
   history or explicit expiry evidence; an empty collection is valid for a new
   account. To verify expiry insights, provide a true user-confirmed due date via
   the inventory event API and observe the resulting rule-generated evidence.
8. Let PURCHASE_CREATED queue the Wallet pass (or use the owned prepare endpoint).
   Confirm SYNCED and verify the Generic object in the real issuer account. Check
   its canonical merchant, timestamp, currency, total and payment status. Request
   the Add-to-Google-Wallet URL and complete Google's save action interactively.
   A signed URL or SYNCED state alone does not prove Google accepted the user's
   save. Re-sync and confirm the same object ID remains. Never store the signed
   URL/JWT in screenshots, logs or reports; it is a bearer capability.

## Recovery and evidence

Receipt transient failures have bounded persisted retries; semantic failures wait
for explicit operator action. After fixing configuration, use
`python -m backend.worker --retry <receipt-id> --once`. This preserves past runs.
Wallet failures use the owned sync endpoint or `--retry-wallet <pass-id> --once`.
Active jobs retain their backoff and leases. A Wallet failure cannot roll back a
purchase or inventory. An assistant failed key retains its failure; retry with a
new key. Existing deterministic tests cover duplicate delivery, lease recovery,
provider timeout/rate-limit/auth errors, ownership and atomic persistence.

Record each live check's date, provider/model and safe outcome separately. Do not
mark live verification complete based on configuration presence, mocks, local demo,
HTTP 200 liveness, or a fabricated signed token. Keep the M11 checkpoint explicit
about checks still awaiting credentials or interactive account access.
