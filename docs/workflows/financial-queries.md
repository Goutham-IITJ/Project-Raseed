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
