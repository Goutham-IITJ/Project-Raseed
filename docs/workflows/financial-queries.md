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
API exposes these structured results independently of the Milestone 6 assistant;
the financial services require no LLM, conversation, insight, or memory integration.

Results are marked DERIVED, identify their local dates/UTC boundaries and filters,
and keep currencies independent. Counts, exact totals, rounded averages/percentages,
payment-evidence coverage, and unknown line-total coverage ground assistant tools.
Date phrases are represented by an allowlisted deterministic period selector,
including last_month. The model never determines amounts or ownership.

See [ADR-008](../decisions/ADR-008-financial-analytics.md) and the
[API contract](../api/api-contract.md) for category bases, payment meaning,
rounding, comparison rules, filters, pagination, and timezone boundaries.
Recurring spending has no approved M5 detection contract; it and budget persistence
remain deferred. Assistant tools delegate to these services instead of adding
independent financial calculations or SQL access.

## Milestone 6 assistant flow

Authenticated conversation/message APIs reserve a durable user message and reply.
AssistantService gives AssistantModel a bounded conversation context and the closed
read registry. Typed calls delegate to AnalyticsService, PurchaseService or
InventoryService; each result or safe failure is recorded before model synthesis.
Final text references successful tool-result scalars by call ID and JSON pointer;
the application resolves those values and persists the reply with its evidence.
Failed turns remain visible and do not manufacture answers.

The implemented tool set is spending summary, category breakdown, merchant spending,
period comparison, filtered purchase history, purchase detail, inventory items/item,
lots/lot, and lot events. get_purchase_history covers the get_purchases family.
Inventory reads preserve event-derived quantities and expiry provenance. No write,
recurring-spending, memory, budget, or external tool is registered. See ADR-009 and
the API contract for synchronous limits, idempotency, audit fields and recovery.

## Milestone 7 context

Relevant explicit long-term memories are retrieved before the model call. The
assistant can read memories and insights through approved tools; memory statements
remain user claims and insight data remains a historical canonical snapshot.
Current financial questions continue through AnalyticsService/PurchaseService.
Explicit memory corrections/deletion use authenticated memory controls. See
[memory and insights](memory-insights.md) for relevance and worker workflows.
