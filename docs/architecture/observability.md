# Raseed V2 Observability and Evaluation

## Structured logs

Every request/job should have correlation metadata such as:

- request_id
- user-scoped operation ID where appropriate
- receipt_id / purchase_id / job_id
- model/provider metadata
- tool execution ID

Never log raw secrets or unnecessary sensitive receipt contents.

## AI telemetry

Record:
- provider/model
- prompt/schema version
- latency
- success/failure
- structured validation outcome
- token/cost telemetry where available

Do not store more sensitive content than required for debugging/audit.

## Metrics

Initial metrics:
- receipt processing latency
- extraction success rate
- semantic validation failure rate
- duplicate upload rate
- worker retry rate
- Wallet sync success rate
- assistant tool error rate
- assistant response latency

## Evaluation datasets

Maintain a controlled set of representative receipts covering:
- clear/simple receipts
- long itemized receipts
- multilingual receipts
- poor-quality images
- PDFs
- missing fields
- tax/discount complexity
- tickets/services

Evaluate extraction at the structured-field level, not only by subjective text quality.

## Agent evaluations

Test whether the assistant:
- selects the right tool
- respects user ownership
- avoids hallucinating financial facts
- asks for clarification when needed
- refuses or requests confirmation for destructive operations
- distinguishes observed/derived/inferred/external claims
