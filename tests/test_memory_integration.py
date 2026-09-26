from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from assistant_fixtures import ScriptedModel, call, calls, final, reference
from fastapi.testclient import TestClient
from m7_fixtures import ALICE, BOB, NOW, app_for
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend.app.assistant.models import Message
from backend.app.memory.models import Memory
from backend.app.memory.schemas import MemoryCreate, MemoryQuery, MemoryUpdate
from backend.app.memory.service import MemoryService

pytestmark = pytest.mark.integration


def save(env, *, owner=None, **changes):
    with env.factory() as session:
        return MemoryService(session, owner or env.alice, clock=lambda: NOW).create(
            MemoryCreate.model_validate(
                {"type": "PREFERENCE", "content": "Vegetarian diet", "topics": ["food"], **changes}
            )
        )


def test_memory_api_crud_versions_and_explicit_provenance(environment):
    with TestClient(app_for(environment)) as client:
        payload = {"type": "PREFERENCE", "content": "Vegetarian diet", "topics": ["food"]}
        response = client.post("/api/v1/memories", headers=ALICE, json=payload)
        assert response.status_code == 201, response.text
        row = response.json()["data"]
        assert row["source"] == "USER_EXPLICIT" and row["provenance"] == "OBSERVED"
        assert row["confidence"] == "1" and row["version"] == 1
        assert "user_id" not in row
        url = f"/api/v1/memories/{row['id']}"
        assert client.get(url, headers=ALICE).status_code == 200
        assert len(client.get("/api/v1/memories", headers=ALICE).json()["data"]) == 1
        update = {**payload, "content": "Vegan diet", "expected_version": 1}
        corrected = client.patch(url, headers=ALICE, json=update)
        assert corrected.status_code == 200, corrected.text
        assert corrected.json()["data"]["version"] == 2
        assert client.patch(url, headers=ALICE, json=update).status_code == 409
        assert client.delete(url, headers=ALICE, params={"expected_version": 1}).status_code == 409
        assert client.delete(url, headers=ALICE, params={"expected_version": 2}).status_code == 204
        assert client.get(url, headers=ALICE).status_code == 404
        assert client.get("/api/v1/memories", headers=ALICE).json()["data"] == []


def test_memory_all_operations_are_owned_and_unknown_fields_rejected(environment):
    row = save(environment)
    url = f"/api/v1/memories/{row.id}"
    with TestClient(app_for(environment)) as client:
        assert client.get(url, headers=BOB).status_code == 404
        assert (
            client.patch(
                url,
                headers=BOB,
                json={"type": "FACT", "content": "Overwrite", "expected_version": 1},
            ).status_code
            == 404
        )
        assert client.delete(url, headers=BOB, params={"expected_version": 1}).status_code == 404
        assert client.get("/api/v1/memories", headers=BOB).json()["data"] == []
        for path in [
            "/api/v1/memories?user_id=x",
            url + "?user_id=x",
            "/api/v1/memories?query=%00",
        ]:
            assert client.get(path, headers=ALICE).status_code == 422
        assert (
            client.post(
                "/api/v1/memories",
                headers=ALICE,
                json={"type": "FACT", "content": "x", "role": "assistant"},
            ).status_code
            == 422
        )
        assert client.delete(url, headers=ALICE).status_code == 422
        assert (
            client.delete(url + "?expected_version=1&user_id=x", headers=ALICE).status_code == 422
        )


def test_relevance_expiry_bounds_topics_and_pagination(environment):
    food = save(environment, topics=[])  # Topic matching also indexes the saved statement.
    goal = save(environment, type="GOAL", content="Save for a bicycle", topics=["goals"])
    save(environment, owner=environment.bob, content="Bob private vegetarian preference")
    expired = save(environment, expires_at=NOW + timedelta(seconds=1))
    with environment.factory() as session:
        service = MemoryService(
            session, environment.alice, clock=lambda: NOW + timedelta(seconds=2)
        )
        assert [row.id for row in service.relevant("What can I eat for dinner?")] == [food.id]
        assert [row.id for row in service.relevant("What are my goals?")] == [goal.id]
        assert service.relevant("What is my saved memory?") == ()
        assert service.relevant("Quasar telescope") == ()
        assert service.relevant(" " * 1001) == ()
        assert len(service.list(MemoryQuery(include_expired=True))) == 3
        assert service.get(expired.id).expires_at <= service.clock()
        page = service.list(MemoryQuery(limit=1))
        assert len(page) == 1
        assert service.list(MemoryQuery(limit=1, offset=1))[0].id != page[0].id
    for i in range(8):
        save(environment, content=(f"Food constraint {i}: " + "🍎" * 950))
    with environment.factory() as session:
        chosen = MemoryService(session, environment.alice, clock=lambda: NOW).relevant(
            "Food choices"
        )
        assert 0 < len(chosen) <= 5
        assert sum(len(row.model_dump_json().encode()) for row in chosen) <= 8192


def test_expiry_and_source_message_are_validated(environment):
    with environment.factory() as session:
        from backend.app.purchases.errors import DomainError, NotFound

        service = MemoryService(session, environment.alice, clock=lambda: NOW)
        with pytest.raises(DomainError):
            service.create(MemoryCreate(type="FACT", content="Expired", expires_at=NOW))
        with pytest.raises(NotFound):
            service.create(
                MemoryCreate(type="FACT", content="Missing source", source_message_id=uuid4())
            )
    model = ScriptedModel(final(), final())
    with TestClient(app_for(environment, model)) as client:
        conv = client.post("/api/v1/assistant/conversations", headers=BOB, json={}).json()["data"][
            "id"
        ]
        turn = client.post(
            f"/api/v1/assistant/conversations/{conv}/messages",
            headers=BOB,
            json={"content": "Hello", "idempotency_key": str(uuid4())},
        ).json()["data"]
        for source in [turn["user_message"]["id"], turn["assistant_message"]["id"]]:
            assert (
                client.post(
                    "/api/v1/memories",
                    headers=ALICE,
                    json={"type": "FACT", "content": "x", "source_message_id": source},
                ).status_code
                == 404
            )
        assert (
            client.post(
                "/api/v1/memories",
                headers=BOB,
                json={
                    "type": "FACT",
                    "content": "Confirmed fact",
                    "source_message_id": turn["user_message"]["id"],
                },
            ).status_code
            == 201
        )
        assert (
            client.post(
                "/api/v1/memories",
                headers=BOB,
                json={
                    "type": "FACT",
                    "content": "x",
                    "source_message_id": turn["assistant_message"]["id"],
                },
            ).status_code
            == 404
        )
        with environment.factory() as session:
            assert session.scalar(select(func.count()).select_from(Memory)) == 1
            message = session.get(Message, turn["user_message"]["id"])
            with pytest.raises(IntegrityError), session.begin_nested():
                session.add(
                    Memory(
                        user_id=environment.alice.id,
                        type="FACT",
                        content="foreign",
                        topics=[],
                        search_text="foreign",
                        source_message_id=message.id,
                        source_conversation_id=message.conversation_id,
                        created_at=NOW,
                        updated_at=NOW,
                    )
                )
                session.flush()


def test_assistant_retrieves_across_conversations_and_respects_correction_deletion(environment):
    row = save(environment)
    save(environment, type="GOAL", content="Bicycle purchase", topics=["goals"])
    save(environment, owner=environment.bob, content="Bob secret diet")
    model = ScriptedModel(
        final(),
        calls(call("get_memories", {"query": "diet"})),
        final(
            "Your saved preference: {{value}}.",
            sources=["call_summary"],
            refs=[reference("/data/items/0/content")],
        ),
        final(),
    )
    with TestClient(app_for(environment, model)) as client:
        for turn_number in range(3):
            conversation = client.post(
                "/api/v1/assistant/conversations", headers=ALICE, json={}
            ).json()["data"]["id"]
            response = client.post(
                f"/api/v1/assistant/conversations/{conversation}/messages",
                headers=ALICE,
                json={"content": "What can I eat for dinner?", "idempotency_key": str(uuid4())},
            )
            assert response.status_code == 201, response.text
            context = model.requests[-1].context.memories
            if turn_number == 0:
                assert len(context) == 1 and context[0]["content"] == "Vegetarian diet"
                with environment.factory() as session:
                    MemoryService(session, environment.alice, clock=lambda: NOW).update(
                        row.id,
                        MemoryUpdate(
                            type="PREFERENCE",
                            content="Vegan diet",
                            topics=["food"],
                            expected_version=1,
                        ),
                    )
            elif turn_number == 1:
                assert context[0]["content"] == "Vegan diet"
                assert (
                    response.json()["data"]["assistant_message"]["content"]
                    == "Your saved preference: Vegan diet."
                )
                with environment.factory() as session:
                    MemoryService(session, environment.alice, clock=lambda: NOW).delete(row.id, 2)
            else:
                assert context == ()
        with environment.factory() as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(Memory)
                    .where(Memory.user_id == environment.alice.id)
                )
                == 1
            )


def test_concurrent_memory_corrections_have_one_winner(environment):
    row = save(environment)

    def correct(content):
        with TestClient(app_for(environment)) as client:
            return client.patch(
                f"/api/v1/memories/{row.id}",
                headers=ALICE,
                json={"type": "PREFERENCE", "content": content, "expected_version": 1},
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(correct, ["Vegan", "Vegetarian"])) == [200, 409]
