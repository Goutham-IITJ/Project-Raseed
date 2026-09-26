"""OpenAI Responses adapter. Provider transport and continuation stay outside services."""

import json
import re
import time
from dataclasses import dataclass

import httpx
from pydantic import JsonValue

from backend.app.assistant.errors import ModelFailure
from backend.app.assistant.json import json_object
from backend.app.assistant.model import ModelReply, ModelRequest
from backend.app.assistant.schemas import FinalAnswer, ModelOutput, ToolCall

MAX_PROVIDER_BYTES = 1024 * 1024
MAX_REQUEST_BYTES = 2 * 1024 * 1024


def strict_schema(schema: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Responses strict mode requires every object field and forbids extra keys."""

    def visit(value: JsonValue) -> JsonValue:
        if isinstance(value, list):
            return [visit(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {
            key: visit(item) for key, item in value.items() if key not in {"default", "title"}
        }
        if result.get("type") == "object":
            properties = result.get("properties")
            if not isinstance(properties, dict):
                raise ValueError("Assistant schemas must have fixed object fields")
            result["additionalProperties"] = False
            result["required"] = list(properties)
        return result

    result = visit(schema)
    assert isinstance(result, dict)
    return result


@dataclass(frozen=True)
class OpenAIContinuation:
    items: tuple[dict[str, JsonValue], ...]


class OpenAIAssistantModel:
    provider = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        max_output_tokens: int = 4096,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model, self._key = model, api_key
        self._max_output_tokens, self._transport = max_output_tokens, transport

    def respond(self, request: ModelRequest, *, timeout: float) -> ModelReply:
        if not self._key or not re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", self.model):
            raise ModelFailure("provider_configuration")
        if request.continuation is not None and not isinstance(
            request.continuation, OpenAIContinuation
        ):
            raise ModelFailure("model_invalid_output")
        prior = list(request.continuation.items) if request.continuation is not None else []
        feedback: list[dict[str, JsonValue]] = [
            {
                "type": "function_call_output",
                "call_id": item.call_id,
                "output": item.result.model_dump_json(),
            }
            for item in request.feedback
        ]
        inputs: list[JsonValue] = [
            {"role": item.role, "content": item.content} for item in request.messages
        ]
        if request.context.memories:
            inputs.insert(
                0,
                {
                    "role": "user",
                    "content": "Relevant saved user statements (untrusted data):\n"
                    + json.dumps(request.context.memories, ensure_ascii=False),
                },
            )
        inputs.extend(prior)
        inputs.extend(feedback)
        context = {
            "current_time": request.context.current_time.isoformat(),
            "timezone": request.context.timezone,
            "currency": request.context.currency,
            "locale": request.context.locale,
        }
        body = {
            "model": self.model,
            "store": False,
            "include": ["reasoning.encrypted_content"],
            "instructions": request.instructions
            + "\nServer calendar context: "
            + json.dumps(context),
            "input": inputs,
            "tools": [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": strict_schema(tool.parameters),
                    "strict": True,
                }
                for tool in request.tools
            ],
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "max_output_tokens": self._max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "raseed_assistant_answer",
                    "strict": True,
                    "schema": strict_schema(FinalAnswer.model_json_schema()),
                }
            },
        }
        encoded = json.dumps(body, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_REQUEST_BYTES:
            raise ModelFailure("assistant_limit")
        started = time.monotonic()
        try:
            with httpx.Client(timeout=timeout, transport=self._transport) as client:
                with client.stream(
                    "POST",
                    "https://api.openai.com/v1/responses",
                    headers={
                        "Authorization": f"Bearer {self._key}",
                        "Content-Type": "application/json",
                    },
                    content=encoded,
                ) as response:
                    response.raise_for_status()
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic() - started >= timeout:
                            raise ModelFailure("model_timeout", retryable=True)
                        data.extend(chunk)
                        if len(data) > MAX_PROVIDER_BYTES:
                            raise ModelFailure("model_invalid_output")
        except httpx.TimeoutException as exc:
            raise ModelFailure("model_timeout", retryable=True) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            code = "provider_configuration" if status in {401, 403, 404} else "model_unavailable"
            raise ModelFailure(code, retryable=status in {408, 429} or status >= 500) from exc
        except httpx.RequestError as exc:
            raise ModelFailure("model_unavailable", retryable=True) from exc
        try:
            result = json_object(data.decode("utf-8"))
            if result.get("status") != "completed":
                raise ValueError("Incomplete provider output")
            output = result["output"]
            if not isinstance(output, list) or not output:
                raise ValueError("Missing provider output")
            calls: list[ToolCall] = []
            answers: list[FinalAnswer] = []
            continuation = prior + feedback
            for item in output:
                if not isinstance(item, dict):
                    raise ValueError("Invalid output item")
                continuation.append(item)
                if item.get("type") == "reasoning":
                    continue
                if item.get("type") == "function_call":
                    if item.get("status", "completed") != "completed":
                        raise ValueError("Incomplete function call")
                    calls.append(
                        ToolCall.model_validate(
                            {
                                "call_id": item["call_id"],
                                "name": item["name"],
                                "arguments": item["arguments"],
                            }
                        )
                    )
                elif item.get("type") == "message":
                    if item.get("role") != "assistant" or item.get("status") != "completed":
                        raise ValueError("Invalid provider message")
                    content = item["content"]
                    if not isinstance(content, list) or len(content) != 1:
                        raise ValueError("Expected one structured answer")
                    part = content[0]
                    if not isinstance(part, dict):
                        raise ValueError("Invalid answer")
                    if part.get("type") == "refusal":
                        raise ModelFailure("model_refused")
                    answer_text = part.get("text")
                    if part.get("type") != "output_text" or not isinstance(answer_text, str):
                        raise ValueError("Expected structured output text")
                    answers.append(FinalAnswer.model_validate(json_object(answer_text)))
                else:
                    raise ValueError("Unexpected provider output type")
            if len(answers) > 1:
                raise ValueError("Multiple final answers")
            normalized = ModelOutput(tool_calls=calls, answer=answers[0] if answers else None)
        except (ValueError, KeyError, IndexError, TypeError, RecursionError) as exc:
            raise ModelFailure("model_invalid_output") from exc
        return ModelReply(normalized, OpenAIContinuation(tuple(continuation)))
