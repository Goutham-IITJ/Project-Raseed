# Raseed V2 Coding Standards

- Keep domain logic independent of FastAPI/Next.js/SDK details.
- Prefer explicit service/repository boundaries.
- Use typed request/response/domain models.
- Use migrations for schema evolution.
- Use exact decimal types for money.
- Avoid global mutable state.
- Never put API calls or SQL directly in UI components.
- Never swallow exceptions silently.
- Make retries explicit and bounded.
- Make async handlers idempotent.
- Write tests around domain invariants and external integration adapters.
- Keep provider-specific AI code behind adapters.
- Document non-obvious architectural decisions with ADRs.
