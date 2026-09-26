"""Provider-neutral assistant boundary. No SDK, HTTP, or persistence dependencies."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from pydantic import JsonValue

from backend.app.assistant.schemas import ModelOutput, ToolResult


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, JsonValue]


@dataclass(frozen=True)
class ContextMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class ModelContext:
    current_time: datetime
    timezone: str
    currency: str
    locale: str
    memories: tuple[dict[str, JsonValue], ...] = ()


@dataclass(frozen=True)
class ToolFeedback:
    call_id: str
    result: ToolResult


@dataclass(frozen=True)
class ModelRequest:
    instructions: str
    context: ModelContext
    messages: tuple[ContextMessage, ...]
    tools: tuple[ToolDefinition, ...]
    feedback: tuple[ToolFeedback, ...] = ()
    # Opaque adapter-owned state, transient and scoped to this turn only.
    continuation: object | None = None


@dataclass(frozen=True)
class ModelReply:
    output: ModelOutput
    continuation: object | None = None


class AssistantModel(Protocol):
    provider: str
    model: str

    def respond(self, request: ModelRequest, *, timeout: float) -> ModelReply: ...
