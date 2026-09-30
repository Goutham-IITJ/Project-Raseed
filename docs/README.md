# Project Raseed V2 Blueprint

This directory is the authoritative product and architecture specification for Raseed V2.

To explore the completed product UI without Firebase credentials, use the
[development-only local demo](implementation/local-demo.md) approved in
[ADR-014](decisions/ADR-014-local-demo.md).

## Source of truth hierarchy

1. Approved documents in `docs/` are the architectural/product contract.
2. Application code is the implementation of that contract.
3. The legacy Streamlit repository is reference/prototype code, not the V2 architectural source of truth.
4. Any material deviation from these documents requires an explicit architecture decision record (ADR).

## Current design status

- Product definition: v0.1
- Domain model: v1.0
- Core workflows: v1.0
- System architecture: v1.0 draft
- Database architecture: v1.0 draft
- API contract: [implemented v1 endpoints](api/api-contract.md)
- AI/worker architecture: v1.0 draft
- Security architecture: v1.0 draft

This blueprint is intentionally implementation-aware but not yet a final coding specification. Technology choices can change through ADRs without changing the core product/domain model.

Milestones 0–1 use the accepted Firebase/SQLAlchemy decisions in
[ADR-004](decisions/ADR-004-identity-foundation.md). Local setup is documented in
[DEVELOPMENT.md](../DEVELOPMENT.md). The Streamlit prototype remains untouched.

Milestone 2 persistence and API clarifications are recorded in
[ADR-005](decisions/ADR-005-canonical-purchase-foundation.md).

Milestone 3 implements private uploads and asynchronous Gemini extraction. The
actual processing/recovery contract is in [receipt ingestion](workflows/receipt-ingestion.md)
and [ADR-006](decisions/ADR-006-receipt-ingestion.md). Local workers, deterministic
checks, and explicit live verification commands are in [DEVELOPMENT.md](../DEVELOPMENT.md).
The completed checks and changed-file inventory are recorded in the
[Milestone 3 validation checkpoint](implementation/milestone-3-validation.md).

Milestone 4 adds event-derived inventory, purchase-event processing, authenticated
stock corrections and expiry provenance. See [inventory](workflows/inventory.md),
[ADR-007](decisions/ADR-007-inventory.md), and the inventory API contract.
Completed checks and files are listed in the
[Milestone 4 validation checkpoint](implementation/milestone-4-validation.md).

Milestone 5 adds deterministic financial analytics and filtered purchase history.
Calculation, currency, date, and API clarifications are in
[ADR-008](decisions/ADR-008-financial-analytics.md) and the financial-query workflow.
Budgets and insight integrations remain deferred. Validation and
the changed-file inventory are in the
[Milestone 5 checkpoint](implementation/milestone-5-validation.md).

Milestone 6 adds persisted conversations, bounded assistant orchestration, and
eleven approved financial/purchase/inventory read tools. See
[ADR-009](decisions/ADR-009-assistant-tools.md), the assistant API contract, and the
[Milestone 6 checkpoint](implementation/milestone-6-validation.md). Long-term
memory and proactive insights build on this foundation in Milestone 7.

Milestone 7 adds explicit long-term memory controls, bounded relevant assistant
recall, and asynchronous canonical spending/inventory insights. See
[ADR-010](decisions/ADR-010-memory-insights.md), the memory/insight API contracts,
[the workflow](workflows/memory-insights.md), and the
[Milestone 7 checkpoint](implementation/milestone-7-validation.md).
Milestone 8 adds the asynchronous Google Wallet projection; see
[ADR-011](decisions/ADR-011-google-wallet.md).

Milestone 9 adds owned asynchronous market searches, external observations,
conservative product/pack comparisons and approved assistant tools. See
[ADR-012](decisions/ADR-012-market-intelligence.md),
[the workflow](workflows/market-intelligence.md) and
[the Milestone 9 checkpoint](implementation/milestone-9-validation.md).
Milestone 10 completes the responsive product interface using the existing
services. See [ADR-013](decisions/ADR-013-product-interface.md) for the minimal
read contracts and [the M10 checkpoint](implementation/milestone-10-validation.md)
for delivered screens and validation. Notifications, budgets, recurrence,
financial mutation tools and operational hardening remain deferred.
