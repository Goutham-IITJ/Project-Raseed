# ADR-010 — Long-term memory and asynchronous insights

## Scope and decisions

M7 implements the blueprint's Memory and Insight entities inside the modular
monolith. This clarifies previously unspecified fields, public contracts, rule
thresholds, and outbox fan-out. PostgreSQL, Firebase ownership, the existing
financial/inventory services, and the separate worker process are retained.

## Memory

Memory is an explicitly saved preference, goal, habit, constraint, or fact, not
conversation history. POST /api/v1/memories records the authenticated user's
confirmation of a typed, bounded statement and optional topics/expiry. Its source
is USER_EXPLICIT, provenance OBSERVED, and confidence 1: this records who asserted
it, not verification of financial truth. An optional source_message_id must be an
owned USER message. No automatic transcript extraction, inference, or silent
profile-setting changes are introduced. In particular a memory does not change
canonical currency/timezone/locale preferences or introduce budget persistence.

GET collection/detail, PATCH detail, and DELETE detail are owned service calls.
PATCH and DELETE require the expected version to reject lost updates. PATCH is an
explicit replacement of content/type/topics/expiry; the source remains attributable
to the user. DELETE removes the memory row. Existing conversation responses/tool
audits remain historical records; deletion prevents future memory retrieval.

Management lists are paginated. Relevant retrieval uses PostgreSQL simple-language
full-text token matching plus a small documented topic vocabulary (food, spending,
inventory, shopping, goals). Common question words map to those topics. Search is
parameterized, owner-scoped, excludes expired rows, and returns deterministic ranked
results. It needs no embeddings or new provider. It is lexical/topic relevance,
not a guarantee of semantic recall. Each assistant turn retrieves at most five
memories, with an 8 KiB context budget. Empty/unrelated queries include none.
Memory context is untrusted data in the provider input, never system instructions.

The assistant gets get_memories, get_insights and get_insight read tools, in
addition to M6's eleven tools. Explicit memory mutations use the public memory
service/API; no model-selected write tool is enabled. User controls therefore
cannot be triggered by instructions in a receipt or saved memory. Numeric claims
still require tool-result references and personal statements cannot override
canonical financial or inventory data.

## Insight rules (insights.v1)

Rules consume existing AnalyticsService and InventoryService views. They do not
read OCR/model output or introduce a second monetary calculation system.

- SPENDING_CHANGE: compare the last completed local calendar month with its
  preceding month through compare_periods. Require at least three purchases in
  each and a positive previous total. Emit when the exact absolute change is at
  least 25% of the previous total, separately for each currency. This is recorded
  spending, not cash flow or a normalized month-length comparison.
- UNUSUAL_PURCHASE: yesterday's largest recorded purchase is at least three times
  the mean of the preceding thirty local calendar days (excluding yesterday),
  with at least five baseline purchases and a positive baseline total. Exact
  rational comparison uses the service's total and count, avoiding rounded-mean
  threshold errors. This is a threshold observation, not fraud or recurrence
  detection. Both service snapshots and their periods are retained.
- INVENTORY_EXPIRY: an owned lot has positive remaining stock and a recorded expiry
  at most three local calendar days away, including dates already passed. Unknown
  expiry and depleted lots produce no insight. The original date, source,
  confidence, provenance, and inventory version are retained. No expiry is guessed
  and no stock is depleted. Wording describes recorded expiry, not food safety.

An InsightGenerator protocol phrases validated candidates; the first implementation
uses deterministic templates and requires no AI credentials. Source data and
calculation metadata are bounded JSONB, with exact amounts as strings, rule version,
thresholds, periods/timezone, and evaluation time. Overall provenance is DERIVED;
expiry evidence keeps its own provenance. Statistical confidence is null where
none is defined; expiry confidence comes directly from its evidence.

Stable owner/rule/period/currency or owner/lot keys prevent duplicate insights.
Refreshes update their evidence and expiry; dismissal survives regeneration.
Missing signals are RESOLVED. Statuses are ACTIVE, READ, DISMISSED, RESOLVED,
EXPIRED. Reads suppress expired entries by default even if the worker is offline.
Spending insights expire at the next local month boundary; unusual-purchase and
inventory observations expire at the next local day boundary. Historical details
remain available with original source data. GET /api/v1/insights and GET detail
are reads; PATCH detail marks READ or DISMISSED with a version guard. No API request
generates insights. The assistant reads structured evidence, not summary alone.

## Worker, fan-out, and scheduling

M4's published_at and retry fields continue to belong to inventory delivery for
PURCHASE_CREATED. A separate set of insight delivery acknowledgement, availability,
attempt, and failure fields on the same outbox rows gives M7 an independent
subscriber for PURCHASE_CREATED and INVENTORY_CHANGED. It never steals inventory
delivery or alters receipt leases. Existing events are marked evaluated during
upgrade; the first scheduled run evaluates existing canonical data.

The poller schedules INSIGHT_EVALUATION_REQUESTED jobs once per owner/local day
and timezone, plus a job per owned lot. Durable unique schedule keys make concurrent
schedulers/restarts safe. Scheduling uses set-based inserts for lot jobs; processing
is bounded to twenty task IDs per dispatch. Purchase jobs evaluate financial rules;
inventory events and scheduled lot jobs evaluate only the linked owned lot.
Daily jobs evaluate financial rules even without new purchases and revisit expiry
as time passes. The worker derives owners from durable foreign-keyed rows.

Short worker transactions lock the event and owner, persist insights and
INSIGHT_CREATED outbox events atomically with acknowledgement. Canonical service
reads use separate sessions and their existing snapshot contracts; no AI/network
call runs under those locks. Separate analytics reads are recorded snapshots, not
a promise of one global cross-service snapshot. Retryable persistence failures
use three attempts with five/ten-second backoff; permanent domain failures are
retained. An operator can requeue an exhausted insight event. Duplicate delivery
does not re-execute acknowledged tasks. INSIGHT_CREATED has no M8 consumer here.

## Migration and limits

0007_memory_insights adds only memories and insights, their indexes/constraints,
and the outbox links/delivery fields described above. All user-owned links use
ownership constraints. Downgrade drops M7 records/jobs only and preserves M1–M6
data and their delivery state. Destructive round trips use only the test database.

Wallet, market intelligence, notifications, budgets, recurrence/duplicate detection,
savings recommendations, currency conversion, AI memory extraction, and UI redesign
remain deferred. No M8 implementation is included.
