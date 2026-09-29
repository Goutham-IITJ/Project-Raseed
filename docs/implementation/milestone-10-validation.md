# M10 product interface validation

Validated on 2026-09-29, continuing the existing uncommitted product interface.
The approved scope replaces the original M10 hardening slot; see
[ADR-013](../decisions/ADR-013-product-interface.md).

## Delivered

- Overview: server spending totals, separate currencies, period comparison,
  categories, recent purchases, inventory attention and insights.
- Purchases: literal merchant/item search, date/category/merchant/payment filters,
  pagination, details, private original viewing and receipt processing status.
- Inventory: quantities and lots, expiry provenance/confidence, activity history,
  and versioned/idempotent consumption, discard and correction actions.
- Insights: type/status filters, evidence/calculation details, read and dismiss.
- Assistant: conversation history, questions, escaped answers and evidence,
  bounded pending-response polling and safe retry keys.
- Wallet: pass status, prepare from purchases, retry/synchronize and validated
  Google Wallet save URLs, without claiming that a pass has been saved.
- Settings: account details, currency/timezone/locale save and profile reload,
  and Firebase session sign-out.
- Add Receipt: file validation, drag/drop or file chooser, upload progress,
  processing/review/failure/completion states and purchase navigation.
- Shared responsive shell, keyboard-accessible dialogs and mobile navigation,
  focus restoration, reduced motion, loading/error/empty states and retry controls.

The original M10 screens and styling were retained. Completion fixes cover
polling stability and bounds, account-switch cancellation, precision-safe currency
formatting, preference refresh, visible receipt-list errors and empty history
pagination. No legacy Streamlit file or database migration changed.

## Checks

| Check | Result |
| --- | --- |
| Frontend Vitest / Testing Library | 33 passed in 5 files |
| Playwright Chromium desktop and mobile | 10 passed |
| Frontend ESLint, zero warnings | Passed |
| TypeScript noEmit | Passed |
| Next.js production build | Passed; all product routes generated |
| Full backend pytest with disposable PostgreSQL | 905 passed |
| Ruff lint | Passed |
| Ruff formatting | Passed; 149 files |
| mypy backend | Passed; 103 source files |
| Git whitespace check | Passed |

Frontend tests cover API auth/cancellation, decimal/date presentation, receipt
validation and processing, bounded polling, account isolation, inventory request
replay, insight evidence/dismissal, Wallet recovery, preferences and assistant
retry/pagination. Browser tests exercise every product route, mobile navigation
and focus, upload-to-purchase flow, original viewing, mutations, assistant
evidence, settings/sign-out, and recovery into empty states at a 320px viewport.

The three additive backend reads are tested for ownership, validation, literal
wildcard escaping, filter/pagination composition and content integrity. The
Assistant retains its prior approved tool schema through a typed history adapter.
The entire existing backend suite passes, including its database integration and
migration tests. No additional architecture or provider behavior was introduced.

## Validation boundaries

Browser tests use isolated Firebase session persistence and intercepted API and
Firebase transports; the real PostgreSQL/backend boundary is verified separately.
Production Firebase verification remains unchanged. Live Google sign-in, receipt
extraction, market providers and Google Wallet require the existing deployment
configuration and were not exercised against external accounts. Playwright needed
normal Windows process permissions to shut down its test server cleanly.

Existing backend dependency warnings remain for Starlette/httpx and Google's
Python 3.10 support. Next.js reports an unrelated lockfile outside the repository;
it is ignored and does not affect the successful build. No secrets are committed.
Budgets, notifications, operator receipt correction, provider expansion and
operational hardening remain deferred.
