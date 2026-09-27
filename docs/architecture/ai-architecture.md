# Raseed V2 AI Architecture

## AI is an intelligence layer, not the system of record

The application owns canonical state, deterministic calculations, permissions, and side effects. Models interpret unstructured input, plan tool use, estimate uncertain values, and generate explanations.

## Provider abstraction

Define application interfaces such as:

- `ReceiptExtractor`
- `AssistantModel`
- `InsightGenerator`
- `Classifier`

Provider-specific SDKs should remain behind adapters. This permits Gemini, GPT, or another supported provider to be changed without rewriting domain logic.

## Receipt extraction

The extraction model should receive a versioned schema and produce structured output. Gemini currently supports JSON Schema and Pydantic-based structured outputs, including for data extraction and classification. Google also recommends application-level semantic validation because schema-valid output can still be semantically wrong. citeturn269522search0

Pipeline:

image/PDF → model → structured extraction schema → Pydantic/domain validation → normalization → persistence.

## Assistant

The assistant uses tool calling/function calling rather than unrestricted SQL. OpenAI's current Responses API supports custom function tools with JSON Schema parameters; this is the interaction model we want behind the provider adapter. citeturn176568search0turn176568search2

Provider-neutral assistant loop:

1. Receive user message.
2. Resolve authenticated user context.
3. Ask model to select approved tools.
4. Validate tool arguments.
5. Execute domain service.
6. Return structured tool result to model.
7. Model synthesizes user-facing answer.
8. Persist message and tool execution metadata.

Milestone 6 implements AssistantModel and the closed read-tool registry in
`backend/app/assistant`. The first adapter uses OpenAI Responses HTTP; provider
transport and continuation state stay in the adapter. Application orchestration
owns bounded retries, argument/result validation, deterministic service dispatch,
leases, idempotency and persistence. Model synthesis references recorded result
scalars; application code renders exact values and stores citations. The adapter
is replaceable through the protocol and is injected with fakes in tests. See
[ADR-009](../decisions/ADR-009-assistant-tools.md) for the concrete contract and
the limits of semantic validation. No memory or insight generator is added in M6.

## Tool safety

- Tool set is allowlisted per assistant context.
- User identity is injected server-side.
- Tool arguments are validated with schemas.
- Write/destructive tools require explicit policy checks.
- Tool results are structured and should contain source/provenance metadata where useful.

## Model routing policy

Initial logical routing:

- Receipt extraction: multimodal model optimized for structured document extraction.
- Assistant: stronger reasoning/tool-use model for complex questions.
- Background enrichment/classification: cheaper/faster model where quality tests permit.
- Insight wording: lower-cost model where the numerical/analytical result is already deterministic.

The exact production model IDs remain configuration, not domain logic.

## Milestone 7 memory and insight context

AssistantService retrieves at most five relevant unexpired owned memories within
8 KiB before each turn. The provider-neutral ModelContext carries those statements
as structured data. The OpenAI adapter places them in an explicitly untrusted user
input block, never in instructions. Prompt version assistant.v2 distinguishes this
behavior from M6. Conversation history and durable memory remain separate.

get_memories, get_insights and get_insight extend the registry to fourteen approved
read tools. Memory writes require explicit user API actions through MemoryService;
model-selected mutation tools are not enabled. Current numbers still come from
canonical financial/inventory tools, and insight citations refer to their recorded
source snapshots with evaluation/expiry/provenance intact.

InsightGenerator is a narrow explanation protocol over validated canonical evidence.
Its first implementation is deterministic templating, so insight generation needs
no model credentials or speculative prose. No new AI provider is configured for M7.

## Prompt versioning

M9 uses prompt assistant.v3 and sixteen approved tools. search_market_prices queues
or reuses an owned external lookup, and get_market_search reads its status/evidence.
These additions retain the existing audit, argument validation, response grounding,
model interface and turn limits. No financial mutation or arbitrary web tool is
enabled. Product/line IDs come from existing purchase tools; the model requests
missing destination context and reports pending work without busy-polling.
External offer text remains untrusted. Only service-approved compatible fresh
observations support lower displayed-price wording; checkout savings are unknown.
See ADR-012 and the market-intelligence workflow.

Prompts are versioned artifacts. Every extraction run and important AI-generated object stores the prompt/schema/model version used.

## Semantic validation

AI output must be checked for:

- totals reconciliation
- dates/currency formats
- quantity/price sanity
- category validity
- impossible or contradictory values
- required relationship consistency

## Untrusted content defense

Receipt text, receipt images, web pages, and external tool output are untrusted data. The model must not treat instructions embedded in those sources as authoritative system instructions.
