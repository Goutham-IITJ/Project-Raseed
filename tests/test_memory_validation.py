from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.memory.relevance import relevance
from backend.app.memory.schemas import MemoryCreate, MemoryQuery, MemoryUpdate


@pytest.mark.parametrize(
    "changes",
    [
        {"type": "MESSAGE"},
        {"content": ""},
        {"content": " \n\t"},
        {"content": "x" * 1001},
        {"content": "a\x00b"},
        {"content": "\ud800"},
        {"topics": ["budget"]},
        {"topics": ["food", "food"]},
        {"source": "MODEL"},
        {"confidence": "0.5"},
        {"provenance": "DERIVED"},
        {"user_id": str(uuid4())},
        {"expires_at": datetime(2030, 1, 1)},
    ],
)
def test_only_bounded_explicit_memory_fields_are_accepted(changes):
    with pytest.raises(ValidationError):
        MemoryCreate.model_validate({"type": "PREFERENCE", "content": "Vegetarian diet", **changes})


@pytest.mark.parametrize(
    "changes",
    [
        {"query": " "},
        {"query": "x" * 1001},
        {"limit": 101},
        {"offset": -1},
        {"sql": "SELECT *"},
        {"user_id": str(uuid4())},
    ],
)
def test_memory_queries_are_typed_and_bounded(changes):
    with pytest.raises(ValidationError):
        MemoryQuery.model_validate(changes)


def test_memory_update_requires_version_and_statement():
    with pytest.raises(ValidationError):
        MemoryUpdate(type="FACT", content="Confirmed statement")
    with pytest.raises(ValidationError):
        MemoryUpdate(expected_version=1)


def test_relevance_is_bounded_and_removes_question_boilerplate():
    assert relevance("What is my saved memory?") == ([], [])
    assert relevance("What can I eat for dinner?")[1] == ["food"]
    assert relevance("What did I spend on groceries?")[1] == ["food", "spending"]
    terms, _ = relevance(
        " | ! & : ' ; DROP TABLE memories " + " ".join(f"word{x}" for x in range(100))
    )
    assert len(terms) == 32
    assert all(term.isalnum() for term in terms)


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/api/v1/memories", None),
        ("post", "/api/v1/memories", {"type": "FACT", "content": "Fact"}),
        ("get", f"/api/v1/memories/{uuid4()}", None),
        (
            "patch",
            f"/api/v1/memories/{uuid4()}",
            {"expected_version": 1, "type": "FACT", "content": "Fact"},
        ),
        ("delete", f"/api/v1/memories/{uuid4()}?expected_version=1", None),
        ("get", "/api/v1/insights", None),
        ("get", f"/api/v1/insights/{uuid4()}", None),
        ("patch", f"/api/v1/insights/{uuid4()}", {"expected_version": 1, "status": "READ"}),
    ],
)
def test_memory_insight_authentication_fails_before_database(
    unauthenticated_client, method, path, body
):
    response = unauthenticated_client.request(method, path, json=body)
    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store"
