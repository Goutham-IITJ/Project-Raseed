# Milestone 8 validation checkpoint

Validated on 2026-09-27 from M7 `a17c454`.

## Result

M8 implements owned WalletPass persistence, a typed WalletProvider boundary,
Google Generic class/object REST integration, stable issuer/purchase identifiers,
and IAM-signed Add-to-Google-Wallet links. The authenticated API ensures, lists,
reads, queues synchronization and issues links for an owned synchronized pass.
No Google credentials or network calls are required at application startup.

The database remains canonical. PURCHASE_CREATED outbox events atomically hand
off to unique durable WalletPass jobs, independently of inventory/insight delivery.
Existing purchases are backfilled in batches of twenty. Google I/O runs outside
database transactions. Three attempts with 5/10-second backoff, bounded Retry-After,
five-minute leases, fenced finalization and explicit requeue handle failures and
crashes. Class/object conflicts and uncertain outcomes converge on stable IDs.

Passes project only canonical merchant, purchase time, currency, exact total and
payment status. They expose no receipt artifact URL, notes or payment instrument.
Signed save links are transient bearer capabilities containing existing object
references. SYNCED means Google API acceptance, not proof of user saving.

See [ADR-011](../decisions/ADR-011-google-wallet.md),
[the Wallet architecture](../architecture/wallet.md), and
[the API contract](../api/api-contract.md#google-wallet-milestone-8).

## Validation

| Check | Result |
| --- | --- |
| `uv run pytest` | 771 passed, zero skipped; 294.20 seconds |
| Focused Wallet suite | 89 passed |
| `uv run ruff check backend tests database` | Passed |
| `uv run ruff format --check backend tests database` | Passed; 131 files |
| `uv run mypy backend` | Passed; 92 source files |
| `uv run alembic upgrade head` | Passed |
| `uv run alembic current` | `0008_google_wallet (head)` |
| `uv run alembic check` | No schema drift |

Tests use real disposable PostgreSQL and fake Wallet providers/mocked Google
REST/IAM transport. The signer test generates a temporary RSA key in memory and
verifies the returned JWT signature/claims without a live Google account. Tests
cover API authentication and ownership, FK/lifecycle constraints, exact amounts,
malformed/provider/credential failures, backoff/exhaustion/manual retry, bounded
batches, concurrent API/handoff duplicates, claims, stale workers, crash after
external success, atomic handoff, stable reconstruction, and earlier migrations.

The full suite retains the two existing dependency warnings for Starlette/httpx
and Google's Python 3.10 support. The test command exports only TEST_DATABASE_URL
from the ignored local `.env`; application configuration retains its existing
pydantic-settings loader. This avoids this installed uv version's embedded-JSON
quote handling in `--env-file` without changing local configuration or test policy.

## Migration and changed scope

`0008_google_wallet` adds wallet_passes and the Wallet-specific outbox handoff
timestamp/index. Upgrade preserves canonical/M1–M7 records and other subscriber
state. Tested downgrade/upgrade drops only local M8 projection state and rebuilds
the same external IDs. Destructive round trips ran only on the test database;
the application database received an upgrade only. No live Google data was changed.

Changes are confined to the new Wallet module/API, configuration and app/worker
wiring, outbox metadata, migration, tests, and authoritative/development docs.
The existing test fixture and migration snapshots include the new M8 schema.

Live Google issuer/credential/publishing verification, managed task deployment,
insight/inventory passes, ticket-specific passes, save callbacks, revocation,
notifications and account association remain deferred. M9 and UI milestones are
not implemented. Legacy Streamlit and frontend code are unchanged. No push occurs.
