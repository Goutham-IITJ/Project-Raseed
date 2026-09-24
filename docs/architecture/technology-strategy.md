# Raseed V2 Technology Strategy

## Selected foundation and later integration candidates

- Frontend: Next.js + TypeScript
- Backend: FastAPI + Python
- Database: PostgreSQL
- ORM: SQLAlchemy 2
- Migrations: Alembic
- Authentication: Firebase Authentication with Google Sign-In; Firebase Web SDK
  in Next.js and Firebase Admin SDK token verification in FastAPI
- Receipt/object storage: private object storage (Google Cloud Storage candidate;
  no public receipt URLs)
- Runtime: Cloud Run or equivalent managed containers
- Async work: outbox + Cloud Tasks/HTTP workers initially
- AI: provider abstraction; Gemini is a natural first receipt-extraction candidate; GPT-class models are candidates for complex tool-using assistant work
- Wallet: Google Wallet API

## Why not microservices initially?

Use modular boundaries without operational fragmentation.

## Why not Streamlit?

The old Streamlit implementation was an interview/demo optimization, not a deliberate long-term architecture. V2 needs a persistent frontend/backend boundary and reusable APIs.

## Technology-change rule

Technology choices are implementation decisions. The product/domain invariants are more stable. A new technology requires an ADR only when it materially changes architecture, cost, security, or operational behavior.
