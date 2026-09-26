# Memory and insight workflows (Milestone 7)

## Explicit long-term memory

User saves a preference/goal/habit/constraint/fact → authenticated MemoryService →
owned Memory row with explicit source, provenance, confidence, optional source USER
message and expiry. No transcript scanning or model-generated persistence occurs.

User opens memory controls → paginated owned list/detail → replacement with expected
version or explicit version-checked deletion. Concurrent stale changes return 409.
Expired records remain manageable but are excluded from assistant retrieval.

Assistant message → relevance query → at most five owned unexpired memories within
8 KiB → model input as untrusted data → approved tools → grounded response. Search
uses simple-language full-text tokens and food/spending/inventory/shopping/goals
topics derived for indexing from the saved statement and explicit topics. A meal
question can match a vegetarian preference without requiring exact word overlap.
This is deterministic lexical/topic matching, not full semantic search. A no-match
query includes no memory. Memory is not canonical financial evidence or a replacement
for actual profile settings. Deleting a memory affects later retrieval; existing
conversation messages and tool audit records remain historical evidence.

## Proactive insights

PURCHASE_CREATED → independent insight subscriber → financial service views →
threshold decisions → source data and deterministic explanation → Insight and
INSIGHT_CREATED committed together with delivery acknowledgement.

INVENTORY_CHANGED → owned lot projection → positive stock and recorded-expiry rule →
insight creation/refresh/resolution. Unknown expiry yields no observation. Changes
to stock or expiry resolve a signal that no longer applies. No quantity is mutated.

The separate worker also schedules durable evaluations once per user/local date
and timezone, including a job for each owned lot. This covers clock-driven expiry
and financial periods even without new domain events. Scheduled jobs, source-event
acknowledgements, retries, and insight keys are persisted. Restart/concurrent
delivery cannot create duplicate logical observations. No request handler generates
insights; GET only reads and filters their stored state.

Default financial rules compare the last two completed months (25% absolute change,
at least three purchases each), and yesterday's largest purchase against the prior
thirty days' mean (three times the mean, at least five baseline purchases). Currency
groups remain separate and exact service values are retained. Inventory observations
include recorded dates within three local days or already passed, with remaining
stock and original date provenance. These are evidence-backed threshold descriptions,
not fraud detection, forecasts, safety guarantees or recommendations.

Insight user controls mark records READ or DISMISSED with version guards. Dismissal
survives reevaluation of the same logical signal. Default reads suppress dismissed,
resolved and expired records; details remain available as historical snapshots.
The assistant can cite structured insight source values through read tools. Current
financial/stock answers still use current canonical services.

See [ADR-010](../decisions/ADR-010-memory-insights.md) and
[the API contract](../api/api-contract.md) for schemas, status, source, retry and
calendar semantics. Wallet/market/notification/budget/recurrence work remains deferred.
