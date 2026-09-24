# Raseed V2 Google Wallet Integration

## Canonical relationship

Raseed database → Wallet integration → Google Wallet.

Wallet state is a projection.

## Google Wallet model

Google Wallet passes are built around Passes Classes and Passes Objects. The class acts as the shared template and the object represents an individual pass instance. Generic passes are available for use cases without a more specific pass type. citeturn269522search1turn269522search2turn269522search4

## Raseed mapping

- `WalletPass` stores provider identifiers and sync status.
- A receipt can map to a Generic pass initially.
- A ticket-like purchase may later use a specific Wallet pass type if the domain data supports it.
- Insight/action projections can be separate pass objects only when they provide user value.

## Issuance

Google Wallet supports issuing passes through signed “Add to Google Wallet” links/JWTs. citeturn269522search7

## Synchronization

Wallet updates are performed asynchronously. A failure to sync Wallet must not roll back the purchase.

## Credentials

Server-side Wallet API operations use managed service credentials. Google documents service-account based authentication for server-side Wallet API access. citeturn269522search5turn269522search6
