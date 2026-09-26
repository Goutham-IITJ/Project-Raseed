import socket
from threading import Thread
from uuid import uuid4

import httpx
import pytest
import uvicorn
from assistant_fixtures import ScriptedModel, call, calls, final, reference
from m7_fixtures import ALICE, BOB, NOW, app_for
from test_insights_integration import job, stock

from backend.app.insights.worker import InsightProcessor

pytestmark = pytest.mark.integration


def test_local_http_memory_assistant_and_insights_against_postgresql(environment):
    env = environment
    lot = stock(env)
    InsightProcessor(env.factory, clock=lambda: NOW).process(job(env, lot_id=lot.id))
    model = ScriptedModel(
        calls(call("get_memories", {"query": "dinner"})),
        final(
            "Your saved preference: {{value}}.",
            sources=["call_summary"],
            refs=[reference("/data/items/0/content")],
        ),
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    host, port = listener.getsockname()
    server = uvicorn.Server(uvicorn.Config(app_for(env, model), log_level="error"))
    thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://{host}:{port}", timeout=15) as client:
            response = client.post(
                "/api/v1/memories",
                headers=ALICE,
                json={"type": "PREFERENCE", "content": "I am vegetarian"},
            )
            assert response.status_code == 201, response.text
            memory = response.json()["data"]
            conversation = client.post(
                "/api/v1/assistant/conversations", headers=ALICE, json={}
            ).json()["data"]["id"]
            turn = client.post(
                f"/api/v1/assistant/conversations/{conversation}/messages",
                headers=ALICE,
                json={"content": "What can I eat for dinner?", "idempotency_key": str(uuid4())},
            )
            assert turn.status_code == 201, turn.text
            assert (
                turn.json()["data"]["assistant_message"]["content"]
                == "Your saved preference: I am vegetarian."
            )
            assert model.requests[0].context.memories[0]["id"] == memory["id"]
            insights = client.get("/api/v1/insights", headers=ALICE).json()["data"]
            assert len(insights) == 1 and insights[0]["type"] == "INVENTORY_EXPIRY"
            assert insights[0]["source_data"]["lot"]["quantity_remaining"] == "2.000000"
            assert (
                client.get(f"/api/v1/insights/{insights[0]['id']}", headers=BOB).status_code == 404
            )
            assert (
                client.patch(
                    f"/api/v1/insights/{insights[0]['id']}",
                    headers=ALICE,
                    json={"status": "DISMISSED", "expected_version": insights[0]["version"]},
                ).status_code
                == 200
            )
            assert client.get("/api/v1/insights", headers=ALICE).json()["data"] == []
            assert (
                client.delete(
                    f"/api/v1/memories/{memory['id']}?expected_version=1", headers=ALICE
                ).status_code
                == 204
            )
            assert client.get("/api/v1/memories?query=dinner", headers=ALICE).json()["data"] == []
            print(
                "Local PostgreSQL HTTP M7: memory controls, relevant assistant recall, "
                "canonical expiry insight, ownership passed."
            )
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        listener.close()
        assert not thread.is_alive()
