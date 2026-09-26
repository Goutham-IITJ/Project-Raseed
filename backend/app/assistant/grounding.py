"""Resolve model-selected citations against recorded results, never model values."""

import re
from collections.abc import Sequence

from pydantic import JsonValue

from backend.app.assistant.errors import AssistantFailure
from backend.app.assistant.models import ToolExecution
from backend.app.assistant.schemas import AnswerEvidence, Citation, FinalAnswer, ToolResult

PLACEHOLDER = re.compile(r"\{\{([a-z][a-z0-9_]{0,39})\}\}")


def _scalar(result: ToolResult, pointer: str) -> str | int | bool | None:
    if not pointer.startswith("/data/") or re.search(r"~(?![01])", pointer):
        raise ValueError("Invalid result pointer")
    value: JsonValue = result.model_dump(mode="json")
    for part in pointer[1:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict):
            value = value[key]
        elif isinstance(value, list) and re.fullmatch(r"0|[1-9][0-9]*", key):
            value = value[int(key)]
        else:
            raise ValueError("Pointer does not identify a value")
    if not (value is None or isinstance(value, (str, int, bool))):
        raise ValueError("References must identify exact scalar values")
    if isinstance(value, str) and (len(value) > 4000 or "\x00" in value):
        raise ValueError("Reference value too large or invalid")
    return value


def _render(value: str | int | bool | None) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def ground_answer(
    answer: FinalAnswer, executions: Sequence[ToolExecution]
) -> tuple[str, AnswerEvidence]:
    try:
        sources = {row.call_id: row for row in executions}
        selected = set(answer.source_call_ids)
        if len(selected) != len(answer.source_call_ids) or not selected <= sources.keys():
            raise ValueError("Unknown or repeated source")
        if answer.kind == "answer" and (
            not selected or any(sources[key].status != "SUCCEEDED" for key in selected)
        ):
            raise ValueError("Data answers need successful current-turn evidence")
        if answer.kind == "unavailable" and not selected:
            raise ValueError("Unavailable answers need an attempted tool")
        names = [reference.name for reference in answer.references]
        placeholders = set(PLACEHOLDER.findall(answer.template))
        if len(names) != len(set(names)) or set(names) != placeholders:
            raise ValueError("Every reference must match a named placeholder")
        prose = PLACEHOLDER.sub("", answer.template)
        if "{{" in prose or "}}" in prose or "\x00" in prose or any(c.isnumeric() for c in prose):
            raise ValueError("Numeric literals must come from tool references")
        citations: list[Citation] = []
        replacements: dict[str, str] = {}
        for reference in answer.references:
            if reference.call_id not in selected:
                raise ValueError("Uncited reference")
            execution = sources[reference.call_id]
            result = ToolResult.model_validate(execution.result)
            if execution.status != "SUCCEEDED" or result.status != "SUCCEEDED":
                raise ValueError("Failed tools cannot supply values")
            value = _scalar(result, reference.pointer)
            citations.append(
                Citation(
                    **reference.model_dump(),
                    tool_execution_id=execution.id,
                    tool_name=execution.tool_name,
                    value=value,
                )
            )
            replacements[reference.name] = _render(value)
        content = PLACEHOLDER.sub(lambda match: replacements[match[1]], answer.template)
        if len(content) > 16000 or not content.strip():
            raise ValueError("Invalid rendered answer size")
        return content, AnswerEvidence(
            kind=answer.kind, source_call_ids=answer.source_call_ids, citations=citations
        )
    except (ValueError, KeyError, IndexError, TypeError, OverflowError) as exc:
        raise AssistantFailure("model_invalid_output") from exc
