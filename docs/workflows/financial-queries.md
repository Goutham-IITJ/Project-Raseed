# Workflow B — Financial Questions

## Principle

The LLM orchestrates and explains; domain services calculate and mutate.

## Flow

User question → Assistant API → intent/query understanding → approved tool selection → domain service → authorized database query/calculation → structured result → LLM synthesis → response with optional provenance.

## Initial tool families

### Read tools
- get_spending_summary
- get_spending_breakdown
- get_purchases
- get_purchase
- get_merchant_spending
- get_recurring_spending
- get_inventory
- get_purchase_history

### Write tools
- mark_item_consumed
- adjust_inventory
- save_memory
- set_budget (future; budget persistence and tool semantics require a later design decision)
- delete/modify records where explicitly authorized

### External tools
- search_market_prices
- product lookup/search

## Rules

- LLM must not receive unrestricted SQL access.
- `user_id` comes from authenticated server context, not model arguments.
- Date phrases such as “last month” are normalized deterministically by application code.
- Numerical answers come from structured tool results.
- Recommendations should cite the evidence used when useful.
- Destructive mutations require confirmation when appropriate.

## Milestone 5 deterministic foundation

AnalyticsService implements spending summaries, direct purchase/line-category
breakdowns, canonical merchant analysis, and period comparisons. PurchaseService
provides filtered history and existing owned purchase detail. The authenticated
API exposes these structured results before the Milestone 6 assistant exists;
no LLM, tool gateway, conversation, insight, or memory integration is introduced.

Results are marked DERIVED, identify their local dates/UTC boundaries and filters,
and keep currencies independent. Counts, exact totals, rounded averages/percentages,
payment-evidence coverage, and unknown line-total coverage can ground later tools.
Date phrases are represented by an allowlisted deterministic period selector,
including last_month. The model never determines amounts or ownership.

See [ADR-008](../decisions/ADR-008-financial-analytics.md) and the
[API contract](../api/api-contract.md) for category bases, payment meaning,
rounding, comparison rules, filters, pagination, and timezone boundaries.
Recurring spending has no approved M5 detection contract; it and budget persistence
remain deferred. Future tools should delegate to these services instead of adding
independent financial calculations or SQL access.
