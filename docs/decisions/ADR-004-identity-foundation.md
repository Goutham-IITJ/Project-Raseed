# ADR-004 — Firebase identity and PostgreSQL user foundation

## Status

Accepted for Milestones 0–1 by the implementation direction.

## Decisions

- Next.js/TypeScript uses Firebase Web SDK Google Sign-In, browser session
  persistence, and refreshed ID tokens. FastAPI verifies bearer ID tokens using
  Firebase Admin SDK, including revocation checks. Server credentials use
  Application Default Credentials; never commit a service-account key.
- The verified Firebase uid maps to a unique `users.firebase_uid`. Application
  ownership uses `users.id` (UUID), never email or a client-supplied user ID.
- SQLAlchemy 2 and Alembic implement PostgreSQL persistence. Provisioning inserts
  with `ON CONFLICT (firebase_uid) DO NOTHING`, then loads the identity in the same
  READ COMMITTED transaction. New users and all initial preferences commit
  together. Unique constraints arbitrate concurrent first requests.
- Only the provisioning repository may look up a user by a verified external
  identity. Every other user-owned repository is constructed with a server-created
  `CurrentUser`; methods do not accept a target user ID.
- `user_preferences` retains the documented key/value model with three supported
  keys. Defaults are INR, Asia/Kolkata, en-IN. User profile columns mirror these
  canonical settings. Updates lock the current user's row and change preferences
  and profile projection atomically. This avoids two competing sources of truth.
- Currency is an uppercase registered three-letter code; timezone is a valid IANA
  name; locale is a recognized language[-Script][-REGION] locale. Nulls, empty
  patches, unsupported keys, and ownership selectors are rejected.
- Verified email and display name are captured on provisioning; subsequent sign-in
  loads the existing profile without overwriting preferences. Email is nullable
  and is not unique. Profile resynchronization is outside this milestone.
- The versioned API and error envelope are defined in `docs/api/api-contract.md`.
- The worker remains a package skeleton. No identity event, budget table, queue,
  AI adapter implementation, or receipt subsystem is introduced in this milestone.

## Consequences

Firebase project configuration is required for real sign-in. Tests use a verifier
interface and real PostgreSQL, without a production authentication bypass.
Google sign-out ends the browser session, not every existing token globally.
The legacy Streamlit application and its dependencies/storage stay separate.

Official verification contract:
https://firebase.google.com/docs/auth/admin/verify-id-tokens
