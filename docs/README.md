# Project Raseed V2 Blueprint

This directory is the authoritative product and architecture specification for Raseed V2.

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
- API contract: [v1 identity and canonical purchase endpoints](api/api-contract.md)
- AI/worker architecture: v1.0 draft
- Security architecture: v1.0 draft

This blueprint is intentionally implementation-aware but not yet a final coding specification. Technology choices can change through ADRs without changing the core product/domain model.

Milestones 0–1 use the accepted Firebase/SQLAlchemy decisions in
[ADR-004](decisions/ADR-004-identity-foundation.md). Local setup is documented in
[DEVELOPMENT.md](../DEVELOPMENT.md). The Streamlit prototype remains untouched.

Milestone 2 persistence and API clarifications are recorded in
[ADR-005](decisions/ADR-005-canonical-purchase-foundation.md).
