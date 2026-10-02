# Raseed V2 Implementation Roadmap

## Milestone 0 — Foundation
- repository structure
- documentation/ADRs
- local development environment
- CI
- linting/type checking/test framework

## Milestone 1 — Identity and database foundation
- Firebase Authentication with Google Sign-In and backend ID-token verification
- users/preferences
- PostgreSQL
- migrations
- repository layer
- `/api/v1/me` and current-user preferences endpoints
- authenticated ownership and concurrent first-login tests
- excludes budget persistence and all receipt/AI/inventory/assistant integrations

## Milestone 2 — Core receipt and purchase model
- receipt metadata and extraction-run schema foundations
- merchant normalization
- purchases
- payments
- line items
- categories/products
- canonical validation, repositories, and domain services
- transaction/outbox foundations for corresponding domain events

## Milestone 3 — Receipt ingestion and extraction
- depends on Milestone 2 schema and services
- private object storage
- receipt API
- async job and outbox dispatch
- versioned extraction schema and provider adapter
- extraction run persistence
- schema/semantic validation and review states
- no inventory consumer until Milestone 4

## Milestone 4 — Inventory
- depends on canonical purchases and ingestion from Milestones 2–3
- inventory lots/items/events
- user corrections
- expiry provenance

## Milestone 5 — Analytics
- spending summary
- category breakdown
- merchant analysis
- period comparisons

Concrete read contracts and financial semantics: [ADR-008](../decisions/ADR-008-financial-analytics.md).
Budget persistence and assistant/insight integrations remain deferred.

## Milestone 6 — Assistant
- conversations/messages
- tool layer
- financial and inventory tools
- grounded responses

Concrete persistence, idempotency, provider, grounding and API contracts:
[ADR-009](../decisions/ADR-009-assistant-tools.md). Read tools reuse the completed
financial/purchase/inventory services. No M7 memory or proactive insights are added.

## Milestone 7 — Insights and memory
- insight generation
- persistent memory
- user controls

Implemented contracts, deterministic rule thresholds, assistant relevance and
independent outbox delivery are specified in
[ADR-010](../decisions/ADR-010-memory-insights.md). Only explicit user-confirmed
memory is saved. Financial/inventory insights run in the existing separate worker.

## Milestone 8 — Google Wallet
- class/object mapping
- issuance
- synchronization
- failure/retry states

Implemented persistence, REST/signing boundary, stable IDs, owned APIs, independent
outbox handoff, leased synchronization and retry contracts:
[ADR-011](../decisions/ADR-011-google-wallet.md). Only canonical purchase Generic
passes are included. Insight/ticket passes, M9 and UI remain deferred.

## Milestone 9 — Market intelligence
- product matching
- external search provider
- normalized price observations

Implemented asynchronous search requests, eBay provider boundary, owned observation
persistence, conservative identity/pack comparison, freshness and assistant tools:
[ADR-012](../decisions/ADR-012-market-intelligence.md) and
[the validation checkpoint](milestone-9-validation.md). No UI milestone is included.

## Milestone 10 — Product interface
- responsive Overview, Analysis, Purchases, Inventory, Insights, Assistant, Wallet and Settings
- authenticated receipt upload, processing status and original receipt viewing
- real API data, explicit provenance and honest loading/error/empty states
- frontend interaction and desktop/mobile browser tests, lint, typecheck and build

The approved M10 scope supersedes the original hardening slot. See
[ADR-013](../decisions/ADR-013-product-interface.md) for the minimal additive read
contracts. Legacy Streamlit and backend service boundaries remain unchanged.
The completed visual redesign is recorded in
[the redesign validation checkpoint](milestone-10-redesign-validation.md).

## Milestone 11 — Real provider integration and verification

- retain the current product interface and existing provider adapters
- verify live Firebase, Gemini, assistant, GCS and Wallet where credentials exist
- exercise the complete receipt-to-Wallet path with deterministic provider boundaries
- validate configuration, readiness, worker recovery, ownership and secret handling
- record live-account prerequisites and distinguish mocks from external acceptance

See [the M11 checkpoint](milestone-11-validation.md),
[provider setup and verification](provider-verification.md) and
[ADR-015](../decisions/ADR-015-provider-verification.md).

## Deferred — Hardening
- security review
- evaluation datasets
- observability
- performance
- deployment
