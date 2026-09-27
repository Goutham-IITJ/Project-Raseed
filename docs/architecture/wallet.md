# Raseed V2 Google Wallet Integration

## Canonical relationship

Implemented M8 contracts: [ADR-011](../decisions/ADR-011-google-wallet.md) and
[Wallet API](../api/api-contract.md#google-wallet-milestone-8).

Raseed database → Wallet integration → Google Wallet.

Wallet state is a projection.

`PURCHASE_CREATED → durable WalletPass → WalletTaskQueue → WalletProcessor →
WalletProvider → Google Generic class/object`. The existing separate poller runs
the worker. A Wallet-only outbox acknowledgement records durable handoff; all
external status, retry and lease state lives on WalletPass. Canonical transactions
and existing inventory/insight acknowledgements are independent of Google failures.

One GOOGLE/GENERIC pass belongs to an owned purchase. Stable IDs derive from the
configured issuer and purchase UUID. Only canonical merchant/time/currency/exact
total/payment status are projected. Purchase records remain immutable in M8.
The worker holds no database transaction during provider I/O. Class/object conflict
handling, bounded backoff, lease fencing and explicit requeue support recovery.

## Google Wallet model

Google Wallet passes are built around Passes Classes and Passes Objects. The class acts as the shared template and the object represents an individual pass instance. Generic passes are available for use cases without a more specific pass type. citeturn269522search1turn269522search2turn269522search4

## Raseed mapping

- `WalletPass` stores provider identifiers and sync status.
- A receipt can map to a Generic pass initially.
- A ticket-like purchase may later use a specific Wallet pass type if the domain data supports it.
- Insight/action projections can be separate pass objects only when they provide user value.

## Issuance

The authenticated add-to-wallet endpoint signs an existing synchronized object
reference through IAM Credentials signJwt. URLs/JWTs are returned transiently;
they are never stored or logged. Saving into Google Wallet is a separate user
action and SYNCED does not assert that it happened. Service accounts need issuer
access; the ADC caller also needs IAM signing permission on the configured signer.

Google Wallet supports issuing passes through signed “Add to Google Wallet” links/JWTs. citeturn269522search7

## Synchronization

Wallet updates are performed asynchronously. A failure to sync Wallet must not roll back the purchase.

## Credentials

Server-side Wallet API operations use managed service credentials. Google documents service-account based authentication for server-side Wallet API access. citeturn269522search5turn269522search6
