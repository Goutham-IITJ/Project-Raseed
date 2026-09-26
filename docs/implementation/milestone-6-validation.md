# Milestone 6 validation checkpoint

Validated on 2026-09-26 from M5 checkpoint `46560b1`.

## Result

The assistant exposes four authenticated conversation/message routes and eleven
approved financial, purchase, and inventory read tools. PostgreSQL stores owned
conversations, ordered messages, tool execution audits, and response evidence.
The provider-neutral orchestration boundary uses an OpenAI Responses HTTP adapter;
financial calculations remain in the existing domain services.

Repeated submissions reuse persisted messages and results. Concurrent turns in
one conversation are rejected, provider retries are bounded, and expired leases
prevent stale executions from replacing recovered failures. Response placeholders
are resolved from recorded tool results, preserving exact decimals and unknowns.
See [ADR-009](../decisions/ADR-009-assistant-tools.md) and the
[API contract](../api/api-contract.md#assistant-milestone-6).

| Check | Result |
| --- | --- |
| Focused assistant and migration suite | 181 passed, zero skipped |
| Complete Python suite with PostgreSQL | 619 passed, zero skipped |
| New assistant tests | 175 passed: 78 validation/authentication, 36 provider, 61 integration |
| Additional M6 migration preservation test | Passed |
| Backend coverage | 97% (3550 of 3645 statements) |
| Assistant package and API coverage | 98% (886 of 902 statements) |
| Ruff check | Passed |
| Ruff format --check | Passed, 93 files |
| mypy backend | Passed, 67 source files |
| Development Alembic upgrade/current | 0006_assistant_tools (head) |
| Alembic check | No schema drift |
| Real PostgreSQL loopback HTTP smoke | Four routes, exact spending, inventory, idempotency, and owner isolation passed |

Commands run:

```powershell
uv run --no-sync --env-file .env pytest tests/test_assistant_validation.py tests/test_assistant_provider.py tests/test_assistant_integration.py tests/test_migrations.py -q --tb=short
uv run --no-sync --env-file .env pytest --cov=backend/app --cov-report=term-missing --cov-report=json:.cache/m6-coverage.json --junitxml=.cache/m6-pytest.xml -q --tb=short
.venv/Scripts/python.exe -m ruff check backend tests database
.venv/Scripts/python.exe -m ruff format --check backend tests database
.venv/Scripts/python.exe -m mypy backend
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic current
.venv/Scripts/python.exe -m alembic check
```

The complete suite includes the HTTP smoke and all migration round trips. Two
existing dependency warnings remain: Starlette/httpx deprecation and Google's
Python 3.10 support notice. Relative links in the updated documentation resolve,
and `git diff --check` passes.

## Evidence and migration

Tests exercise all approved tools against canonical purchases and inventory;
mixed currencies, period boundaries, category bases, empty data, and exact amounts;
and foreign-owner rejection at the API, tool, repository, and database boundaries.
Unapproved tools, owner selectors, SQL, malformed JSON, oversized payloads,
fabricated values, and invalid citations fail without inventing results.

Lifecycle checks cover submission replay/conflicts, duplicate tool calls,
transient provider retries, persisted terminal errors, time and invocation limits,
concurrent requests, and recovery during both model and tool execution. Tests
confirm that provider calls hold no database transaction or conversation lock.
Context is bounded by message count and bytes and remains private to a conversation.

The HTTP smoke starts a real loopback server against disposable PostgreSQL. It
verifies exact `0.300000 INR` spending and `3.000000` remaining inventory, then
confirms another owner's `999.000000` spending stays in that owner's conversation.
Authentication and model responses are injected only into the test-created app.
The OpenAI transport tests use HTTP mocks and verify strict tool/final schemas,
transient reasoning continuation, size limits, refusal handling, and safe errors.
No live AI or cloud account is contacted.

Revision `0006_assistant_tools` adds conversations, messages, and tool executions,
with composite ownership foreign keys, idempotency and ordering constraints, and
one active reply per conversation. The M6 downgrade/upgrade test preserves the
existing canonical rows and checks execution-state constraints and model/schema
agreement. Destructive tests use only the separate `raseed_test` database.
The development database was upgraded without a downgrade.

## Files changed

Application and configuration:

- `backend/app/assistant/`: model boundary, provider adapter, closed tool registry,
  orchestration, persistence, schemas, grounding, prompt, and safe errors.
- `backend/app/api/assistant.py`
- `backend/app/main.py`
- `backend/app/config.py`
- `.env.example`

Migration and tests:

- `database/migrations/env.py`
- `database/migrations/versions/0006_assistant_tools.py`
- `tests/conftest.py`
- `tests/assistant_fixtures.py`
- `tests/test_assistant_validation.py`
- `tests/test_assistant_provider.py`
- `tests/test_assistant_integration.py`
- `tests/test_migrations.py`

Documentation:

- `DEVELOPMENT.md`
- `docs/README.md`
- `docs/api/api-contract.md`
- `docs/architecture/ai-architecture.md`
- `docs/data/database.md`
- `docs/domain/domain-model.md`
- `docs/decisions/ADR-009-assistant-tools.md`
- `docs/implementation/roadmap.md`
- `docs/implementation/milestone-6-validation.md`
- `docs/workflows/financial-queries.md`

## Boundaries and deferrals

Live provider/account access has not been verified. Configure `OPENAI_API_KEY` and
`ASSISTANT_MODEL` in the ignored local environment to enable real assistant turns.
Conversation creation and reads work without model credentials; message submission
then records a safe configuration failure. Receipt extraction retains its separate
Gemini configuration.

Grounding validates cited value origin and rendering, not every semantic claim in
natural-language prose. Assistant wording remains INFERRED. Canonical financial
and inventory data remain the source of truth.

Long-term memory, proactive insights, budgets, recurring patterns, assistant writes,
streaming/background turns, Wallet, market intelligence, UI work, and legacy changes
remain deferred. No Milestone 7 feature is introduced.
