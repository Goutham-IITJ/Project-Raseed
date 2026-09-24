# ADR-002 — PostgreSQL as Canonical Application Database

## Status
Accepted (initial V2 direction)

## Decision
Use PostgreSQL for canonical structured data.

## Rationale
Raseed has relational ownership, purchases, line items, payments, inventory events, conversations, insights, and synchronization state. Exact monetary types, foreign keys, transactions, constraints, and migrations are valuable.

Alternative paths such as Firestore can be reconsidered through an ADR if product or operational requirements change.
