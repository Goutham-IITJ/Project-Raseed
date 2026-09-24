# Raseed V2 System Architecture

## Architectural style

**Modular monolith + asynchronous workers.**

The first version should not be decomposed into many independently deployed microservices. Internal modules define clear domain boundaries; background workers handle long-running or retryable work.

## Logical components

### Web application
- Next.js + TypeScript
- user-facing upload, dashboard, inventory, assistant, insights, and settings

### API/backend
- FastAPI + Python
- authentication middleware
- request validation
- domain/application services
- repositories
- tool gateway for the assistant

### PostgreSQL
Canonical relational application state.

### Object storage
Receipt images/PDFs and other user-owned artifacts.

### Task/worker layer
Asynchronous receipt processing, wallet sync, insight generation, memory extraction, scheduled analytics.

### External systems
- AI model providers
- Google Wallet
- market/product information providers
- Firebase Authentication (Google Sign-In)

## High-level topology

Web → API → Domain Services → PostgreSQL
                     │
                     ├→ Object Storage
                     └→ Outbox → Task Queue → Workers

Workers integrate with AI providers and external systems while writing durable status back to PostgreSQL.
