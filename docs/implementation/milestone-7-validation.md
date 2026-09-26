# Milestone 7 validation checkpoint

Validated on 2026-09-26 from the completed M6 working tree over M5 `46560b1`.
The final M7 commit also records that previously uncommitted M6 foundation.

## Result

Long-term memory has typed explicit user statements, source/provenance/confidence,
optional expiry and owned USER-message attribution, versioned correction/deletion,
management/search APIs and bounded relevant assistant retrieval. It is separate
from conversation history; no transcript is automatically saved.

The insight worker generates spending-change, unusually large purchase and
recorded-inventory-expiry observations from existing canonical services. Structured
source snapshots, versioned rules, confidence where defined, timestamps, status and
expiry accompany deterministic explanations. Currency and amount semantics remain
those of the existing analytics/inventory modules.

Independent outbox delivery state preserves the inventory subscriber. Durable daily
scheduling, bounded dispatch/retry, idempotent insight keys and outgoing
INSIGHT_CREATED events remain in the existing separate worker. No API generates
insights. User controls mark observations read/dismissed; dismissal survives refresh.

Assistant prompt assistant.v2 retrieves at most five relevant unexpired memories
within 8 KiB and passes them as untrusted data. Three new read tools bring the
registry to fourteen. Cited numbers still resolve from recorded tool evidence.
See [ADR-010](../decisions/ADR-010-memory-insights.md),
[the API contract](../api/api-contract.md), and
[the workflow](../workflows/memory-insights.md).

## Validation

| Check | Result |
| --- | --- |
| Full Python suite with disposable PostgreSQL | 682 passed, zero skipped |
| Backend coverage | 97% (4191 of 4301 statements) |
| Memory service / insight evaluation coverage | 100% / 100% |
| Focused memory and empty-schema checks | 36 passed |
| Focused insight and existing migration checks | 30 passed |
| M7 round trip, HTTP, memory and provider checks | 45 passed |
| Ruff check / format | Passed; 116 files formatted |
| mypy backend | Passed; 83 source files |
| Frontend lint / typecheck / test / build | Passed; 4 tests |
| Development migration and schema drift | 0007_memory_insights (head); no schema drift |

The suite retains two existing dependency notices: Starlette/httpx deprecation and
Google's Python 3.10 support notice. Frontend build also reports an ignored lockfile
outside the repository; all four frontend checks succeed. Relative documentation
links resolve and `git diff --check` passes.

Commands:

```powershell
uv run --env-file .env pytest --cov=backend/app --cov-report=term-missing --cov-report=json:.cache/m7-coverage.json --junitxml=.cache/m7-pytest.xml -q --tb=short
uv run ruff check backend tests database
uv run ruff format --check backend tests database
uv run mypy backend
uv run alembic upgrade head
uv run alembic current
uv run alembic check
npm.cmd --prefix apps/web run lint
npm.cmd --prefix apps/web run typecheck
npm.cmd --prefix apps/web test
npm.cmd --prefix apps/web run build
```

The env-file option supplies TEST_DATABASE_URL; integration tests execute against
the separate disposable PostgreSQL database and are not skipped. They cover
ownership at HTTP/service/tool/FK boundaries, version conflicts, concurrent memory
corrections, source attribution, expiry, relevance/byte bounds, future-conversation
recall, correction/deletion, untrusted provider input and no automatic message capture.

Insight tests cover exact threshold boundaries and minimum evidence, low ambient
Decimal precision, separate currencies/owners, empty data, recorded versus unknown
expiry, depleted-stock resolution, status/expiry/dismissal, source evidence,
independent subscriber acknowledgements, rollback of insight and outgoing event
together, retry/backoff/exhaustion/requeue, duplicate delivery, concurrent daily
scheduling, bounded batches and clock-driven reevaluation. M7 downgrade/upgrade
preserves canonical data, M6 conversations/messages and original outbox state.

The real loopback HTTP smoke saves a vegetarian preference without explicit topics,
retrieves it for a dinner question in the assistant, reads an expiry insight with
exact `2.000000` remaining stock, dismisses it, deletes the memory, and verifies
owner isolation. Authentication/model boundaries are test injections; HTTP and
PostgreSQL are real. M7 insight generation requires no AI provider.

## Files and scope

- New `backend/app/memory/` and `backend/app/insights/` modules and their API routers.
- Assistant context, tools, provider input and prompt-version integration.
- Outbox model and `backend/worker/__main__.py` scheduling/dispatch/requeue integration.
- `database/migrations/versions/0007_memory_insights.py` and migration model imports.
- M7 fixtures, memory/insight/API/HTTP/migration tests and updated M6 registry expectations.
- ADR-010, API/domain/data/worker/AI/workflow documentation, roadmap and development guide.

M8, Wallet, market intelligence, notifications, budgets, recurrence/duplicate
detection, currency conversion, unsupported recommendations, automatic AI memory
extraction and model-selected memory mutations remain deferred. No legacy Streamlit
or frontend feature redesign is included. Live OpenAI account/model access remains
unverified; all provider tests use mocked HTTP transport.
