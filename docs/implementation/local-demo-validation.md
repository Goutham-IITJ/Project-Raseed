# Local demo validation — 2026-09-30

Continued from the committed M10 interface (`bcdbc1f`), preserving its screens
and domain model. The existing PostgreSQL validation cluster was reused. Its
disposable test database uses UTC sessions, matching the Compose environment;
the separately seeded `_demo` database was never reset by tests.

| Check | Result |
| --- | --- |
| Full backend pytest, real PostgreSQL | 927 passed, zero skipped |
| Demo-specific backend cases (included above) | 22 passed |
| Frontend Vitest / Testing Library | 37 passed |
| Normal Firebase desktop/mobile Playwright | 10 passed |
| Real demo API/database desktop/mobile Playwright | 6 passed |
| ESLint, zero warnings | Passed |
| TypeScript noEmit | Passed |
| Next.js production build, demo disabled | Passed |
| Next.js production build, demo enabled | Rejected as required |
| Backend Ruff lint / formatting / mypy | Passed |
| Git whitespace check | Passed |

Demo tests verify explicit flags, production and hosted-runtime rejection,
loopback restrictions, the single fixed credential, unchanged Firebase selection,
ownership isolation, concurrent/idempotent seeding, preservation of preferences,
and rollback of an interrupted seed including new receipt artifacts.

Browser tests use the real seeded API without Firebase credentials, token
injection, API interception or external requests. They exercise Overview,
Purchases and private originals, Inventory and expiry evidence, Insights,
Assistant and grounded sample citations, Wallet states, Settings, Add Receipt,
sign-out/re-entry, desktop/mobile layout and the visible synthetic-data notice.
The standard Firebase browser suite remains separate and unchanged.

The seed contains 24 purchases, four merchants/categories/receipts, six products,
29 lines, six inventory lots with events, four rule-derived inventory insights,
three memories, three conversations/six messages, and five Wallet states.
Existing services calculate all displayed financial and inventory values.

No new migrations, legacy Streamlit edits, provider expansion or future milestone
work is included. Live assistant/market/Wallet actions and the external worker
are disabled in demo; local uploads remain queued. Dates remain anchored to the
first seed. PostgreSQL and Python/Node dependencies are still required.

Existing warnings remain for Starlette/httpx, Google's Python 3.10 support and
Next.js's ignored lockfile outside this repository. No credentials or generated
database, receipt, screenshot or trace artifacts are committed.

Exact setup and restart commands: [local-demo.md](local-demo.md).
