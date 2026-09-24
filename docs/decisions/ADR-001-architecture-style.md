# ADR-001 — Modular Monolith + Asynchronous Workers

## Status
Accepted (initial V2 direction)

## Decision
Use a modular monolith for the primary backend, with asynchronous worker processes for expensive/retryable tasks.

## Why
Raseed needs clear domain boundaries and background processing but does not yet require the operational complexity of many independently deployed microservices.

## Consequences
Positive:
- simpler local development
- shared domain model
- easier debugging
- clear internal module boundaries
- workers can scale independently

Trade-off:
- future extraction of high-load domains may require deliberate module interfaces
