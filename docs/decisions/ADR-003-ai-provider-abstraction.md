# ADR-003 — Provider-Abstraction for AI

## Status
Accepted (initial V2 direction)

## Decision
Application code uses provider-neutral AI interfaces and adapter modules.

Logical interfaces:
- ReceiptExtractor
- AssistantModel
- InsightGenerator
- Classifier

The exact provider/model is configuration and can change independently of domain services.
