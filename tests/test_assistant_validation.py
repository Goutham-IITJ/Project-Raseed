from types import SimpleNamespace
from uuid import uuid4

import pytest
from assistant_fixtures import call, final, reference
from pydantic import ValidationError

from backend.app.assistant import tools as assistant_tools
from backend.app.assistant.errors import AssistantFailure
from backend.app.assistant.grounding import ground_answer
from backend.app.assistant.json import call_hash, json_object
from backend.app.assistant.schemas import (
    ConversationCreate,
    FinalAnswer,
    MessageCreate,
    ModelOutput,
    ToolCall,
    ToolResult,
)
from backend.app.assistant.tools import ToolRegistry


@pytest.mark.parametrize(
    "content",
    ["", " \n\t", "x" * 8001, "a\x00b", None, "\ud800"],
    ids=["empty", "blank", "oversized", "nul", "null", "surrogate"],
)
def test_message_content_is_bounded_nonblank_and_postgres_safe(content):
    with pytest.raises(ValidationError):
        MessageCreate(content=content, idempotency_key=uuid4())


@pytest.mark.parametrize("field", ["user_id", "role", "status", "model", "sql", "tool_calls"])
def test_client_cannot_supply_assistant_control_fields(field):
    with pytest.raises(ValidationError):
        MessageCreate.model_validate(
            {"content": "Hello", "idempotency_key": str(uuid4()), field: "chosen"}
        )


@pytest.mark.parametrize("title", ["", " ", "x" * 201, "a\x00b", "\ud800"])
def test_conversation_title_validation(title):
    with pytest.raises(ValidationError):
        ConversationCreate(title=title)


def test_conversation_and_message_require_their_documented_fields():
    assert ConversationCreate().title is None
    with pytest.raises(ValidationError):
        ConversationCreate.model_validate({"user_id": str(uuid4())})
    with pytest.raises(ValidationError):
        MessageCreate(content="Hello")
    with pytest.raises(ValidationError):
        MessageCreate(content="Hello", idempotency_key="invalid")


def test_registry_contains_only_typed_approved_read_tools():
    definitions = ToolRegistry().definitions()
    assert {tool.name for tool in definitions} == {
        "get_memories",
        "get_insights",
        "get_insight",
        "get_spending_summary",
        "get_spending_breakdown",
        "get_merchant_spending",
        "get_period_comparison",
        "get_purchase_history",
        "get_purchase",
        "get_inventory",
        "get_inventory_item",
        "get_inventory_lots",
        "get_inventory_lot",
        "get_inventory_events",
    }
    assert len(definitions) == 14
    for tool in definitions:
        assert tool.parameters["type"] == "object"
        assert tool.parameters["additionalProperties"] is False
        assert (
            not {"user_id", "firebase_uid", "sql", "connection", "role"}
            & tool.parameters["properties"].keys()
        )
        if "query" in tool.parameters["properties"]:
            # M7 permits bounded natural-language relevance, never a SQL query.
            assert tool.name == "get_memories"
            assert tool.parameters["properties"]["query"]["maxLength"] == 1000


def test_duplicate_tool_registration_fails_closed(monkeypatch):
    tool = assistant_tools.approved_tools()[0]
    monkeypatch.setattr(assistant_tools, "approved_tools", lambda: (tool, tool))
    with pytest.raises(ValueError, match="Duplicate"):
        ToolRegistry()


@pytest.mark.parametrize(
    "arguments",
    [
        '{"user_id":"chosen"}',
        '{"sql":"SELECT * FROM users"}',
        "not json",
        "[]",
        "null",
        '{"limit":true}',
        '{"limit":1.5}',
        '{"limit":0}',
        '{"limit":101}',
        '{"offset":10001}',
        '{"currency":"usd"}',
        '{"period":"arbitrary"}',
        '{"start_date":"2026-09-01"}',
        '{"period":"today","start_date":"2026-09-01","end_date":"2026-09-02"}',
        '{"limit":1,"limit":2}',
        '{"limit":NaN}',
        '{"limit":1e999}',
        '{"purchase_type":"\\u0000"}',
        '{"merchant_id":"not-a-uuid"}',
    ],
)
def test_invalid_tool_arguments_never_reach_a_service(arguments):
    outcome = ToolRegistry().invoke(None, call("get_purchase_history", arguments))
    assert outcome.arguments is None
    assert outcome.result.status == "FAILED"
    assert outcome.result.data is None
    assert outcome.result.error.code == "invalid_arguments"


@pytest.mark.parametrize(
    "name", ["execute_sql", "__getattribute__", "set_budget", "adjust_inventory", "save_memory"]
)
def test_unknown_and_write_tools_have_no_dispatch_path(name):
    outcome = ToolRegistry().invoke(None, call(name, {"sql": "DROP TABLE users"}))
    assert outcome.result.error.code == "unknown_tool"
    assert outcome.result.data is None


def test_call_identity_is_stable_for_key_order_and_whitespace_only():
    assert call_hash("x", '{"a":1,"b":2}') == call_hash("x", '{ "b": 2, "a": 1 }')
    assert call_hash("x", "invalid") == call_hash("x", "invalid")
    assert call_hash("x", "invalid") != call_hash("x", "invalid ")
    assert call_hash("x", "{}") != call_hash("y", "{}")
    assert json_object('{"text":"\\\\u0000"}') == {"text": "\\u0000"}


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"answer": None, "tool_calls": []},
        {"answer": final().output.answer, "tool_calls": [call()]},
    ],
)
def test_model_must_choose_calls_or_answer_exclusively(value):
    with pytest.raises(ValidationError):
        ModelOutput.model_validate(value)


@pytest.mark.parametrize(
    "changes",
    [
        {"call_id": ""},
        {"call_id": "a b"},
        {"arguments": "x" * 16385},
        {"arguments": "\u20b9" * 6000},
        {"name": "\x00"},
    ],
)
def test_tool_calls_are_bounded_before_persistence(changes):
    with pytest.raises(ValidationError):
        ToolCall.model_validate({**call().model_dump(), **changes})


def execution(data=None, *, status="SUCCEEDED", call_id="call_summary"):
    result = ToolResult(
        status="SUCCEEDED", data=data or {"total": "0.300000", "currency": "INR", "unknown": None}
    )
    if status == "FAILED":
        result = ToolResult.failure("not_found", "Resource not found.")
    return SimpleNamespace(
        id=uuid4(),
        call_id=call_id,
        tool_name="get_spending_summary",
        status=status,
        result=result.model_dump(mode="json"),
    )


def test_grounding_inserts_exact_recorded_scalars_and_persists_citations():
    row = execution()
    answer = final(
        "Recorded total: {{value}} {{currency}}. Tax: {{unknown}}.",
        sources=[row.call_id],
        refs=[
            reference("/data/total"),
            reference("/data/currency", name="currency"),
            reference("/data/unknown", name="unknown"),
        ],
    ).output.answer
    text, evidence = ground_answer(answer, [row])
    assert text == "Recorded total: 0.300000 INR. Tax: unknown."
    assert evidence.citations[0].value == "0.300000"
    assert evidence.citations[0].tool_execution_id == row.id
    assert evidence.citations[2].value is None


@pytest.mark.parametrize(
    "pointer",
    [
        "/total",
        "/data/missing",
        "/data",
        "/data/rows/01",
        "/data/rows/-1",
        "/data/rows/2",
        "/data/rows",
        "/data/a~2b",
    ],
)
def test_grounding_rejects_invalid_or_nonscalar_references(pointer):
    row = execution({"rows": ["1"], "a/b": "2"})
    answer = final(
        "Value {{value}}", sources=[row.call_id], refs=[reference(pointer)]
    ).output.answer
    with pytest.raises(AssistantFailure) as error:
        ground_answer(answer, [row])
    assert error.value.code == "model_invalid_output"


def test_json_pointer_escaping_boolean_and_null_are_explicit():
    row = execution({"a/b": {"~key": True}, "rows": [None]})
    answer = final(
        "{{value}} {{unknown}}",
        sources=[row.call_id],
        refs=[reference("/data/a~1b/~0key"), reference("/data/rows/0", name="unknown")],
    ).output.answer
    content, _ = ground_answer(answer, [row])
    assert content == "true unknown"


@pytest.mark.parametrize(
    "template",
    ["Spent 0.31", "Spent \u096a", "Spent \u00bd", "{{missing}}", "{{broken"],
)
def test_grounding_rejects_numeric_literals_and_invalid_templates(template):
    refs = [reference("/data/total")] if "{{value}}" in template else []
    answer = final(template, sources=["call_summary"], refs=refs).output.answer
    with pytest.raises(AssistantFailure):
        ground_answer(answer, [execution()])


@pytest.mark.parametrize("template", ["\x00", "\ud800"])
def test_invalid_unicode_model_text_is_rejected_before_persistence(template):
    with pytest.raises(ValidationError):
        final(template)


def test_grounding_cannot_use_failed_foreign_or_previous_turn_results():
    answer = final(
        "{{value}}", sources=["call_summary"], refs=[reference("/data/total")]
    ).output.answer
    for rows in ([], [execution(status="FAILED")], [execution(call_id="another_turn")]):
        with pytest.raises(AssistantFailure):
            ground_answer(answer, rows)


def test_empty_success_and_handled_failure_can_be_explained_without_inventing_values():
    content, evidence = ground_answer(
        final("No matching recorded purchases.", sources=["call_summary"]).output.answer,
        [execution({"currencies": []})],
    )
    assert content == "No matching recorded purchases." and evidence.citations == []
    answer = final(
        "The data could not be read.", sources=["call_summary"], kind="unavailable"
    ).output.answer
    assert ground_answer(answer, [execution(status="FAILED")])[0] == "The data could not be read."


def test_model_cannot_supply_result_values_or_uncited_answers():
    with pytest.raises(ValidationError):
        FinalAnswer.model_validate(
            {**final().output.answer.model_dump(), "calculated_total": "999"}
        )
    with pytest.raises(AssistantFailure):
        ground_answer(final("Recorded purchases.", kind="answer").output.answer, [])
    with pytest.raises(AssistantFailure):
        ground_answer(final("Unavailable.", kind="unavailable").output.answer, [])


def test_failed_tool_result_cannot_contain_fabricated_data():
    with pytest.raises(ValidationError):
        ToolResult(
            status="FAILED", data={"total": "9"}, error={"code": "failure", "message": "Failed"}
        )
    with pytest.raises(ValidationError):
        ToolResult(status="SUCCEEDED", error={"code": "failure", "message": "Failed"})


@pytest.mark.parametrize(
    "method,suffix",
    [
        ("post", ""),
        ("get", "/00000000-0000-0000-0000-000000000000"),
        ("get", "/00000000-0000-0000-0000-000000000000/messages"),
        ("post", "/00000000-0000-0000-0000-000000000000/messages"),
    ],
)
def test_assistant_authentication_rejects_before_database_access(
    unauthenticated_client, method, suffix
):
    response = unauthenticated_client.request(
        method, "/api/v1/assistant/conversations" + suffix, json={}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert response.headers["Cache-Control"] == "no-store"
