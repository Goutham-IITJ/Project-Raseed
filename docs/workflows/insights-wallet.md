# Workflow D — Insights and Wallet

## Insight pipeline

Domain event → Insight evaluation → structured metrics → insight record → explanation generation → optional delivery.

Examples:
- spending change
- unusual spending
- budget progress (future; depends on a later budget-persistence design decision)
- recurring/duplicate patterns
- savings opportunity

## Wallet principle

Google Wallet is a projection of Raseed state, not the canonical source of truth.

Raseed stores the purchase, insight, and synchronization state. A dedicated Wallet integration service translates Raseed state into Google Wallet pass classes/objects and issues or updates them.

## Typical events

PURCHASE_CREATED → receipt Wallet sync / analytics / insight evaluation
INVENTORY_CHANGED → optional Wallet projection refresh
INSIGHT_CREATED → optional insight pass update

## Failure handling

Wallet failures do not roll back the canonical purchase transaction. They create a retryable synchronization state.
