# Raseed API v1 — identity foundation

## Transport, versioning, authentication

JSON endpoints live under `/api/v1`. Breaking contracts require a new API version
and ADR. Use HTTPS in production. CORS permits explicitly configured web origins.
Every endpoint below requires `Authorization: Bearer <Firebase ID token>`.
The Firebase Admin SDK verifies tokens; uid resolves to an internal UUID through
concurrency-safe first-request provisioning. No Raseed session cookie is issued.

Ownership comes exclusively from verified server context. These endpoints accept
no query parameters, user ID, Firebase uid, or email as an ownership selector.
Unknown body fields and query parameters are rejected with 422. Unauthenticated
requests are rejected before provisioning or reading user data.

## Success responses

All listed endpoints return HTTP 200 and `{"data": ...}`. UUIDs are strings and
timestamps are ISO 8601 UTC values. Responses use `Cache-Control: no-store`.

### GET /api/v1/me

Returns `data` with `id`, `firebase_uid`, nullable `email` and `display_name`,
`currency`, `timezone`, `locale`, `created_at`, and `updated_at`.

### GET /api/v1/me/preferences

```json
{"data":{"currency":"INR","timezone":"Asia/Kolkata","locale":"en-IN"}}
```

### PATCH /api/v1/me/preferences

Supply one or more of `currency`, `timezone`, `locale`. Omitted settings remain
unchanged. Null values, an empty object, unknown fields, and invalid values return
422. Currency is uppercase ISO 4217; timezone is an IANA name; locale is a
recognized language[-Script][-REGION] tag, normalized to hyphenated form.

```json
{"currency":"USD","timezone":"America/New_York","locale":"en-US"}
```

Returns the full preferences object in the same envelope as GET. Updates affect
only the authenticated user, with preference rows and user profile projection
committed atomically. Concurrent partial updates preserve unrelated fields.

## Errors

```json
{"error":{"code":"unauthorized","message":"A valid bearer token is required."}}
```

- 401 `unauthorized`: missing, malformed, expired, revoked, or otherwise invalid
  token; includes `WWW-Authenticate: Bearer`.
- 422 `validation_error`: invalid body, unsupported field/query, or setting value.
- 503 `authentication_unavailable`: identity verification infrastructure unavailable.
- 503 `database_unavailable`: database operation unavailable.
- 500 `internal_error`: unexpected failure, without internal details or token contents.
- Other HTTP errors use this envelope (for example 404 `http_error`).

## Operational endpoint

`GET /health` is an unauthenticated liveness check returning `{"status":"ok"}`.
It does not provision users or imply database/Firebase readiness. API docs are
available at `/docs`. No other product API is implemented in Milestones 0–1.
