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

## Milestone 6 — Assistant
- conversations/messages
- tool layer
- financial and inventory tools
- grounded responses

## Milestone 7 — Insights and memory
- insight generation
- persistent memory
- user controls

## Milestone 8 — Google Wallet
- class/object mapping
- issuance
- synchronization
- failure/retry states

## Milestone 9 — Market intelligence
- product matching
- external search provider
- normalized price observations

## Milestone 10 — Hardening
- security review
- evaluation datasets
- observability
- performance
- deployment
