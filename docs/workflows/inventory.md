# Workflow C — Inventory

## Principle

Purchase history does not prove current physical inventory.

## Inventory flow

Purchase → InventoryLot → InventoryEvent history → Current InventoryItem state.

## Event types

- PURCHASED
- CONSUMED
- EXPIRED
- DISCARDED
- RETURNED
- MANUAL_ADJUSTMENT
- CORRECTION

## Expiry semantics

Every expiry estimate stores:
- date
- source
- confidence

Sources include RECEIPT, USER, PRODUCT_KNOWLEDGE, MODEL_ESTIMATE, UNKNOWN.

Never present an inferred expiry as an observed fact.

## User corrections

User actions create explicit inventory events. Do not silently overwrite inventory quantity.

Examples:
- “I finished the shampoo.” → CONSUMED event.
- “I still have one.” → USER correction event.
