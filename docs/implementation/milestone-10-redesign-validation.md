# M10 product redesign validation — 2026-10-01

Completed the existing M10 working tree in its approved forest, green and lime
visual direction. This checkpoint supplements the original
[M10 validation](milestone-10-validation.md) and follows
[ADR-013](../decisions/ADR-013-product-interface.md).

## Delivered

- Overview with spending hierarchy, currency selection, period comparison,
  interactive trend, category ring, purchases, inventory attention and merchants.
- Analysis with calendar/custom periods, currency/category/merchant filters,
  trend, previous-period comparison, category comparison, merchant ranking and
  recorded payment distribution. Filter labels remain visible across periods.
- Purchases with grouped history, desktop selection and receipt detail preview,
  a full-detail link, filters, receipt inbox and private original viewing.
- Inventory attention cards, quantities, lots, provenance, activity and update
  dialogs; Insights with a lead observation, supporting records and evidence.
- Assistant conversation navigation, transcript, evidence and composer; Wallet
  purchase passes and recovery states; Settings account/preferences/session rows.
- Add Receipt with file selection, upload progress and processing/review states.
- Shared responsive navigation, mobile quick links, spacing, typography, focus,
  error/empty/loading states and reduced-motion support. Chart points use one
  keyboard tab stop plus arrow/Home/End navigation, with an exact-value table.

Financial values come from existing services. The two analytics reads already
present in the interrupted working tree were retained, formatted and verified
against PostgreSQL. No backend architecture, schema, external provider contract,
or legacy Streamlit behavior changed. Unknown category amounts and absent values
in partial result pages stay unavailable; they are not presented as zero.

## Checks

| Check | Result |
| --- | --- |
| `npm.cmd --prefix apps/web test` | 42 passed in 7 files |
| `npm.cmd --prefix apps/web run lint` | Passed, zero warnings |
| `npm.cmd --prefix apps/web run typecheck` | Passed |
| `npm.cmd --prefix apps/web run build` | Passed, including Analysis and detail routes |
| `npm.cmd --prefix apps/web run test:e2e` | 12 passed, Chromium desktop/mobile |
| `npm.cmd --prefix apps/web run test:demo` | 6 passed, real HTTP/PostgreSQL |
| Analytics PostgreSQL integration suite | 54 passed |
| Ruff on changed analytics code/tests and mypy backend | Passed |
| Git whitespace check | Passed |

Browser suites use separate Next.js output directories so the running local demo
can remain available. Windows requires normal process permissions for Playwright
server cleanup. Generated browser/build files are ignored.

The running demo at `http://127.0.0.1:3000` was inspected at 1440, 768, 390 and
320 pixels across Overview, Analysis, Purchases, Inventory, Insights, Assistant,
Wallet, Settings and Add Receipt. Detail inspection includes original receipts,
inventory lots/update dialogs, saved assistant evidence and expired insight
evidence. No horizontal page overflow or unexpected browser/API errors remained.
Screenshots and inspection reports are local ignored artifacts under
`.cache/m10-validation/`.

The original seeded demo database was preserved. The additional browser suite
used a separate `raseed_redesign_demo` database and the existing idempotent demo
seed. Backend integration tests used only `raseed_validation_test`.

## Remaining boundaries

- Demo uploads stay queued; live assistant and Google Wallet actions are disabled.
  Synced sample passes explicitly state that nothing was issued to Google.
- Receipt review still requires support; no correction endpoint is implied.
- Analytics uses leading categories/merchants and bounded filter choices. Currencies
  are separate and no conversion, budgeting or notification feature is added.
- Existing demo dates are preserved. Select a historical period or expired insight
  status to inspect older records; a quiet current period is a valid empty state.
- Live Firebase sign-in and external extraction/Wallet/market providers were not
  exercised. Normal browser tests use the existing isolated transport fixtures;
  demo tests use the real local API and database without interception.
