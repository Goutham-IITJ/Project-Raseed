# ADR-015 — M11 provider verification and operational readiness

M11 retains the existing Firebase, Gemini, OpenAI Responses, GCS and Google Wallet
adapters, domain services, worker and UI. Live verification requires real account
credentials; deterministic tests remain independent of external accounts.

Add `GET /ready` as an unauthenticated operational endpoint alongside `/health`.
It returns 200 with `{"status":"ready"}` only when PostgreSQL is reachable, its
Alembic revision matches this checkout, and normal-mode Firebase project
configuration is present (or the guarded local demo is enabled). Otherwise it
returns 503 with `{"status":"not_ready"}`. It exposes no configuration values,
database errors or provider details and uses `Cache-Control: no-store`.

This is local API readiness, not proof of valid ADC, live sign-in, model access,
bucket permissions, worker progress or Wallet issuance. No external provider call
occurs at startup or in either health endpoint. Provider failures continue to use
the existing explicit API and durable job states. Deployment verification must
check the worker and providers separately. Database connection/pool waits and the
readiness query are bounded. No new infrastructure or product API is introduced.

CORS and Wallet origins must be complete HTTP(S) origins without credentials,
paths, wildcards or URL suffixes. Production remote origins require HTTPS;
loopback HTTP remains supported for local development with demo disabled.
GCS rejects its SDK emulator override, matching the existing Firebase prohibition:
the production adapters cannot silently select an emulator. Credential/transport
errors remain safe at the adapter and worker CLI boundaries.

Receipt/inventory eligibility, review rules, source-of-truth data and Wallet
projection semantics remain unchanged. A fresh catalog does not auto-enroll
unknown items; the existing explicit inventory enrollment API is used when needed.
