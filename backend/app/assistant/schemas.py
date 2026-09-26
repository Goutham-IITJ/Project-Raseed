from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from backend.app.purchases.schemas import InputModel, nonblank

MAX_ARGUMENT_BYTES = 16 * 1024
MAX_RESULT_BYTES = 64 * 1024
PROMPT_VERSION = "assistant.v2"
SCHEMA_VERSION = "assistant-answer.v1"

CallID = Annotated[str, Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")]


def valid_text(value: str) -> str:
    if "\x00" in value:
        raise ValueError("NUL is not valid assistant content")
    value.encode("utf-8")  # Reject lone Unicode surrogates before PostgreSQL persistence.
    return nonblank(value)


class ConversationCreate(InputModel):
    title: Annotated[str, Field(min_length=1, max_length=200)] | None = None

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str | None) -> str | None:
        return valid_text(value) if value is not None else None


class MessageCreate(InputModel):
    content: Annotated[str, Field(min_length=1, max_length=8000)]
    idempotency_key: UUID

    _content = field_validator("content")(valid_text)


class ToolCall(InputModel):
    call_id: CallID
    name: Annotated[str, Field(min_length=1, max_length=100)]
    # Keep invalid JSON for the audit and let the tool boundary reject it.
    arguments: Annotated[str, Field(max_length=MAX_ARGUMENT_BYTES)]

    @field_validator("arguments", "name")
    @classmethod
    def bounded_text(cls, value: str) -> str:
        if "\x00" in value or len(value.encode("utf-8")) > MAX_ARGUMENT_BYTES:
            raise ValueError("Invalid tool call text")
        return value


class ValueReference(InputModel):
    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
    call_id: CallID
    pointer: Annotated[str, Field(min_length=1, max_length=500)]


class FinalAnswer(InputModel):
    kind: Literal["answer", "clarification", "unavailable"]
    template: Annotated[str, Field(min_length=1, max_length=8000)]
    source_call_ids: Annotated[list[CallID], Field(max_length=8)]
    references: Annotated[list[ValueReference], Field(max_length=40)]

    _template = field_validator("template")(valid_text)


class ModelOutput(InputModel):
    tool_calls: Annotated[list[ToolCall], Field(max_length=8)] = Field(default_factory=list)
    answer: FinalAnswer | None = None

    @model_validator(mode="after")
    def one_output_kind(self) -> "ModelOutput":
        if bool(self.tool_calls) == (self.answer is not None):
            raise ValueError("Return tool calls or a final answer, exclusively")
        return self


class ToolError(InputModel):
    code: str
    message: str


class ToolResult(InputModel):
    status: Literal["SUCCEEDED", "FAILED"]
    data: JsonValue = None
    error: ToolError | None = None

    @model_validator(mode="after")
    def valid_result(self) -> "ToolResult":
        if (self.status == "FAILED") != (self.error is not None):
            raise ValueError("Only failed results have an error")
        if self.status == "FAILED" and self.data is not None:
            raise ValueError("Failed executions cannot claim result data")
        return self

    @classmethod
    def failure(cls, code: str, message: str) -> "ToolResult":
        return cls(status="FAILED", error=ToolError(code=code, message=message))


class Citation(InputModel):
    name: str
    call_id: str
    tool_execution_id: UUID
    tool_name: str
    pointer: str
    value: str | int | bool | None


class AnswerEvidence(InputModel):
    kind: Literal["answer", "clarification", "unavailable"]
    source_call_ids: list[str]
    citations: list[Citation]


class ConversationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ToolExecutionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    message_id: UUID
    call_id: str
    tool_name: str
    raw_arguments: str
    arguments: dict[str, JsonValue] | None
    result: ToolResult | None
    status: Literal["RUNNING", "SUCCEEDED", "FAILED"]
    started_at: datetime
    completed_at: datetime | None
    elapsed_ms: int | None


class MessageView(BaseModel):
    id: UUID
    conversation_id: UUID
    sequence: int
    role: Literal["USER", "ASSISTANT"]
    status: Literal["PROCESSING", "COMPLETED", "FAILED"]
    content: str | None
    reply_to_id: UUID | None
    idempotency_key: UUID | None
    provenance: Literal["OBSERVED", "INFERRED"]
    evidence: AnswerEvidence | None
    provider: str | None
    model: str | None
    prompt_version: str | None
    schema_version: str | None
    model_attempts: int
    failure_code: str | None
    failure_message: str | None
    created_at: datetime
    completed_at: datetime | None
    tool_executions: list[ToolExecutionView]


class TurnView(BaseModel):
    user_message: MessageView
    assistant_message: MessageView
    replayed: bool


class ConversationResponse(BaseModel):
    data: ConversationView


class MessageListResponse(BaseModel):
    data: list[MessageView]


class TurnResponse(BaseModel):
    data: TurnView
