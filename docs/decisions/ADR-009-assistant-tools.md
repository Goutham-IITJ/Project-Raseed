# ADR-009 — Assistant conversations and approved read tools

## Status and scope

Implementation clarification for the requested Milestone 6, within the approved
modular monolith, PostgreSQL, and provider-neutral AssistantModel boundary. The
blueprint names conversations, messages, and tool executions but does not specify
their fields or HTTP contracts. This ADR defines those details and the four
requested assistant routes. No additional entity, worker, or outbox event is added.

## Ownership and persistence

Conversations belong to the authenticated CurrentUser. Messages and tool executions
carry composite ownership foreign keys to their conversation. Repository queries
always include that owner; missing and foreign conversations have the same 404.
Neither message bodies nor tool arguments accept an identity, role, SQL expression,
provider choice, or database connection. The model receives no internal user ID,
Firebase identity, credentials, or another conversation's history.

POST messages requires nonblank content and a UUID idempotency_key. A short
transaction locks the conversation and reserves consecutive USER and ASSISTANT
messages. The user message is COMPLETED; its unique reply starts PROCESSING.
Only one reply may be PROCESSING per conversation. An identical key/content replay
returns the existing pair without calling the provider or tools; changed content
under the same key and a competing new turn return 409. Completed replays return
200, active replays 202, and a new completed pair 201. Failed replays return the
same safe error. An explicit retry uses a new key and retains the failed history.

A processing reply has a random lease token and an expiry of the turn time limit
plus thirty seconds. Every model-attempt, tool, and final write checks the token
and status. The next message POST closes expired replies and any RUNNING tools as
FAILED. A returning stale worker cannot overwrite that failure or a newer turn.
There is no automatic restart after process loss. GET is read-only; it reports
persisted status. Recovery occurs on the next POST, including a same-key replay.

Tool executions record the associated assistant message, provider call ID, tool
name, bounded raw arguments, validated arguments when available, structured result
or safe error, status, UTC start/end times, and elapsed milliseconds. A unique
(message, call ID) prevents duplicate execution. An identical repeated call ID
replays the original success or failure. A changed name/argument payload under
the same ID fails the turn without replacing its audit record. JSON object key
order and whitespace do not change the argument identity; malformed JSON is
compared verbatim. Different call IDs are separate reads and may see newer data.

## Tool boundary

The closed registry exposes:

- get_spending_summary, get_spending_breakdown, get_merchant_spending,
  get_period_comparison: the existing M5 query schemas and AnalyticsService.
- get_purchase_history and get_purchase: PurchaseService's filtered history and
  owned detail. History covers the blueprint's get_purchases family as well.
- get_inventory, get_inventory_item, get_inventory_lots, get_inventory_lot,
  get_inventory_events: existing InventoryService reads and pagination.

There are no write tools or client-callable tool execution endpoint. Extra
arguments (including user_id and sql) are rejected. Unknown tools, malformed
arguments, unavailable records, service failures, and oversized results produce
persisted structured errors that the model can explain or correct within the turn
limits. Tool results are never invented, silently truncated, or replaced by model
output. Large reads must be narrowed or paginated. Payment instrument references,
provider metadata, and last-four digits are omitted from purchase tool projections.

Financial/date/currency/category semantics remain ADR-008's. Tools serialize exact
Decimal amounts as strings, delegate all calculations, and preserve provenance and
empty/null coverage. Each tool uses its service's transaction and snapshot rules;
separate tools do not promise a shared snapshot. A turn fixes its clock for named
period resolution and inventory date status. Recorded tool results are the evidence
for that response even if underlying records later change.

## Orchestration and synthesis

The bounded synchronous loop selects tools, validates and persists executions,
passes the recorded results to the model, validates synthesis, then persists the
reply. No database transaction remains open during provider I/O or retry backoff.
Defaults: six model rounds, eight tool invocations, two attempts per model request,
twenty seconds per provider request, and a two-minute turn budget. Retries apply
only to transient transport/timeout/408/429/5xx failures. Invalid output,
configuration errors, refusal, and exhausted limits fail safely. Tool failures
are not invisibly retried; the model may request another read with a new call ID.
Repeated IDs also count toward the invocation limit.

AssistantModel consumes typed context, bounded recent conversation messages,
allowlisted tool schemas, and tool feedback. It returns typed tool calls or a
structured final answer. History is limited to twenty completed messages and
64 KiB; old messages are omitted as whole messages. History prose is not current
financial evidence. User text, catalog names, notes, and tool output are untrusted
data and cannot authorize extra tools or override instructions.

Final synthesis contains a text template, source call IDs, and named JSON-pointer
references into successful results from this turn. The application resolves those
scalars from persisted tool results, inserts their exact values, and stores the
resolved citations alongside the rendered plain-text reply. Raw numeric literals
outside placeholders, missing/failed sources, invalid pointers, and unused or
missing reference names are rejected. A data answer requires a successful source;
clarification and unavailable-data replies are explicit answer kinds. Empty
successful results can support an explanation without pretending they contain
records. Null values render as unknown, never as zero.

This validates the origin and exact rendering of cited values; it is not a proof
of every semantic claim in natural language. Explanatory prose remains INFERRED,
and prompts prohibit uncited numeric claims (including numbers written as words),
invented facts, and arithmetic. Canonical tools remain the numeric source of truth.
Clients must render content as plain text or safely escaped Markdown.

## First provider adapter

The OpenAI Responses HTTP adapter is isolated from orchestration/domain services.
It uses function schemas, strict structured final output, store:false, and only
the registry's functions. The model ID and secret key are configuration with no
hardcoded model default. No network call occurs at startup. Missing configuration
produces a persisted safe failure when a message is submitted. Tests inject fake
AssistantModel implementations and mock the provider HTTP transport.

Provider continuation items, including encrypted reasoning needed between tool
rounds, remain transient and confined to one turn. No reasoning text, raw provider
response, provider conversation ID, or secret is persisted or returned by the API.
The adapter bounds response/request sizes and rejects incomplete, malformed,
unexpected, or mixed tool/final output. Provider errors never expose response bodies.

References checked during implementation:
https://developers.openai.com/api/docs/guides/function-calling
https://developers.openai.com/api/docs/guides/structured-outputs
https://developers.openai.com/api/docs/guides/reasoning

## API and migration

The API contract documents POST/GET conversation and POST/GET conversation messages,
pagination, status fields, tool audit views, and safe failure envelopes. Reads expose
no leases, owner IDs, credentials, or raw provider state. Assistant failures use
502 (invalid/refused output or orchestration limits), 503 (configuration/unavailable
provider), or 504 (timeout/expired execution); persisted failure codes distinguish
them. All routes use existing authentication, validation, and no-store behavior.

Revision 0006_assistant_tools adds only conversations, messages, and tool_executions.
Indexes support owned conversation access, ordered message pages, per-message tool
history, idempotency, reply uniqueness, and the one-active-turn invariant. Upgrade
preserves all M1–M5 data. Downgrade removes assistant history only; destructive
round trips run exclusively on the disposable test database.

## Deferrals

Long-term memory, proactive insights, budgets, recurring-pattern detection, currency
conversion, assistant writes, streaming/background turns, Wallet, market intelligence,
notifications, UI work, and legacy changes remain outside M6. No M7 work is added.
