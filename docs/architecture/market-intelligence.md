# Raseed V2 Market Intelligence

## Scope

This subsystem answers questions that require current external information, such as:

- “Can I get this product cheaper?”
- “What is the current price of a comparable product?”

## Boundary

Internal Raseed purchase history and external market observations are separate data domains.

User purchase:
- source = user's receipt
- historical fact

Market observation:
- source = external provider
- observed_at timestamp
- merchant/source/location/pack-size context

## Flow

Assistant intent → identify product → external search/lookup adapter → normalize candidate offers → compare like-for-like → persist optional observation → LLM explanation.

## Guardrails

- Never compare different pack sizes without making that explicit.
- Preserve observation timestamp.
- Preserve source/provider and location where applicable.
- Separate displayed price from shipping/tax when possible.
- Do not state that a price is “current” without a recent observation.
- External web content is untrusted input.
