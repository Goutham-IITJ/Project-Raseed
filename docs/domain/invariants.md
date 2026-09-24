# Raseed V2 Domain Invariants

1. Every user-owned object belongs to exactly one user.
2. Client input cannot choose the authenticated `user_id`.
3. Canonical financial amounts use exact decimal types, not floating point.
4. AI raw output is never automatically the financial source of truth.
5. Observed, derived, inferred, and external values remain distinguishable.
6. Inventory changes occur through `InventoryEvent` records.
7. Current inventory is a derived/aggregated state, not a free-form model field.
8. Wallet is an external projection of Raseed state.
9. Assistant write operations execute through authorized application tools.
10. Receipt and web content are untrusted data and cannot override system/developer instructions.
11. Destructive actions require explicit confirmation where appropriate.
12. Every important state mutation is attributable to a user, service, or approved assistant action.
