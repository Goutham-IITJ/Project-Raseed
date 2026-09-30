# Raseed V2 Security Architecture

## Authentication

Use Firebase Authentication with Google Sign-In. The Next.js frontend uses the
Firebase Web SDK with browser session persistence, obtains a Firebase ID token,
and sends `Authorization: Bearer <token>` to FastAPI over HTTPS in production.
The backend verifies tokens with Firebase Admin SDK (including revocation and
disabled-user checks), derives the verified Firebase uid, and maps it to the
internal UUID. No frontend user identifier is accepted as authorization.

Firebase manages token refresh. There is no separate Raseed session cookie or
refresh-token endpoint. Signing out clears the browser Firebase session; it does
not globally revoke already issued ID tokens. Only the configured Firebase
project is trusted. Production verification is never bypassed; tests substitute
the verifier interface. Auth emulator tokens are not supported by this foundation.

See [ADR-004](../decisions/ADR-004-identity-foundation.md) and the
[API contract](../api/api-contract.md).

The optional development-only local demo in
[ADR-014](../decisions/ADR-014-local-demo.md) uses a single fixed fixture identity,
explicit environment gates, a dedicated local database and request-origin/peer
checks. It is disabled by default and rejected by production configuration.
The Firebase production adapter and normal ownership repositories are unchanged.

## Authorization

Every domain query and mutation is scoped to the authenticated user. Never trust client-supplied user IDs.

## Receipt files

Store receipts privately. Access through authorized backend flows and short-lived signed URLs where appropriate.

## Secrets

API keys, OAuth secrets, Wallet service credentials, and database credentials must come from a secret manager/environment configuration, never from source control.

## AI isolation

Models never receive database credentials. They interact through approved domain tools.

## Destructive actions

Deletion, broad inventory changes, and other destructive mutations require explicit policy checks and confirmation when appropriate.

## Provenance

Store enough metadata to distinguish observed, derived, inferred, and external values and to understand why an AI-generated claim exists.

## Prompt-injection defense

Receipt text, uploaded files, websites, market data, and model tool results are untrusted. Their content must never override system instructions, authorization policy, or tool permissions.
