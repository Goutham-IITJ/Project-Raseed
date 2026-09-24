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

## Prompt versioning

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
