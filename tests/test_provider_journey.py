"""Real HTTP/PostgreSQL/local files; external authentication and HTTP are mocked.

This exercises the production adapters, not live provider account acceptance.
"""

import base64
import json
import socket
from datetime import datetime, timezone
from threading import Thread
from typing import Annotated
from uuid import uuid4

import httpx
import pytest
import uvicorn
from assistant_fixtures import final, reference
from fastapi import Depends
from fastapi.testclient import TestClient
from firebase_admin import auth
from ingestion_fixtures import document, evidence
from sqlalchemy.orm import Session
from test_assistant_provider import function_call, message
from wallet_fixtures import wallet_settings

from backend.app.api.dependencies import get_current_user, get_session
from backend.app.api.insights import get_insight_service
from backend.app.assistant.openai import OpenAIAssistantModel
from backend.app.database import make_session_factory
from backend.app.identity.context import CurrentUser
from backend.app.identity.firebase import FirebaseTokenVerifier
from backend.app.ingestion.gemini import GeminiReceiptExtractor
from backend.app.ingestion.service import LocalTaskQueue, OutboxDispatcher, ReceiptProcessor
from backend.app.ingestion.storage import LocalStorageProvider
from backend.app.insights.service import InsightService
from backend.app.insights.worker import InsightDispatcher, InsightProcessor, LocalInsightTaskQueue
from backend.app.inventory.worker import (
    InventoryDispatcher,
    InventoryProcessor,
    LocalInventoryTaskQueue,
)
from backend.app.main import create_app
from backend.app.wallet.google import GoogleWalletProvider
from backend.app.wallet.worker import LocalWalletTaskQueue, WalletDispatcher, WalletProcessor

pytestmark = pytest.mark.integration
ALICE = {"Authorization": "Bearer alice-token"}
BOB = {"Authorization": "Bearer bob-token"}
NOW = datetime(2030, 9, 26, 6, tzinfo=timezone.utc)
PERIOD = {"start_date": "2026-09-01", "end_date": "2026-10-01", "currency": "INR"}


def test_readiness_checks_real_database_revision_without_contacting_providers(
    database, monkeypatch
):
    settings = wallet_settings(firebase_project_id="test-project")
    app = create_app(settings, session_factory=make_session_factory(database))
    with TestClient(app) as client:
        assert client.get("/ready").json() == {"status": "ready"}
        monkeypatch.setattr("backend.app.readiness.schema_heads", lambda: frozenset({"future"}))
        response = client.get("/ready")
        assert response.status_code == 503 and response.json() == {"status": "not_ready"}
        assert client.get("/health").status_code == 200


def test_http_receipt_to_wallet_with_real_adapters_and_mocked_providers(
    database, tmp_path, monkeypatch
):
    factory = make_session_factory(database)
    settings = wallet_settings(firebase_project_id="test-project", local_storage_path=tmp_path)
    storage = LocalStorageProvider(tmp_path)
    provider_calls = {"gemini": [], "assistant": [], "wallet": [], "signing": []}
    verified_tokens = []
    verifier = FirebaseTokenVerifier("test-project")
    sdk_app = object()
    monkeypatch.setattr(verifier, "_get_app", lambda: sdk_app)

    def verify(token, *, app, check_revoked):
        assert app is sdk_app and check_revoked is True
        verified_tokens.append(token)
        if token not in {"alice-token", "bob-token"}:
            raise auth.InvalidIdTokenError("fixture rejected")
        return {"uid": "firebase-" + token.removesuffix("-token")}

    monkeypatch.setattr(auth, "verify_id_token", verify)

    def gemini(request):
        body = json.loads(request.content)
        inline = body["contents"][0]["parts"][0]["inlineData"]
        provider_calls["gemini"].append(base64.b64decode(inline["data"]))
        output = evidence()
        output["line_items"][0]["unit"] = "each"
        if len(provider_calls["gemini"]) == 2:
            output["purchase_time"] = None
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(output)}]}}
                ]
            },
        )

    def assistant(request):
        body = json.loads(request.content)
        provider_calls["assistant"].append(body)
        assert body["store"] is False
        if len(provider_calls["assistant"]) == 1:
            output = function_call(arguments=json.dumps(PERIOD))
        else:
            feedback = body["input"][-1]
            assert feedback["type"] == "function_call_output"
            result = json.loads(feedback["output"])
            assert result["data"]["currencies"][0]["total_spent"] == "11.000000"
            output = message(
                final(
                    "Your recorded spending is {{value}} INR.",
                    sources=["call_summary"],
                    refs=[reference("/data/currencies/0/total_spent")],
                ).output.answer
            )
        return httpx.Response(200, json={"status": "completed", "output": [output]})

    def wallet(request):
        body = json.loads(request.content)
        if request.url.host == "iamcredentials.googleapis.com":
            provider_calls["signing"].append(json.loads(body["payload"]))
            return httpx.Response(200, json={"signedJwt": "test.only.signature"})
        provider_calls["wallet"].append(body)
        return httpx.Response(200, json=body)

    extractor = GeminiReceiptExtractor(
        "fixture-key", "fixture-model", transport=httpx.MockTransport(gemini)
    )
    model = OpenAIAssistantModel(
        "fixture-key", "fixture-model", transport=httpx.MockTransport(assistant)
    )
    wallet_provider = GoogleWalletProvider(
        settings, token_supplier=lambda: "fixture-access", transport=httpx.MockTransport(wallet)
    )
    app = create_app(
        settings,
        verifier=verifier,
        session_factory=factory,
        storage=storage,
        assistant_model=model,
        wallet_provider=wallet_provider,
    )

    def insights(
        user: Annotated[CurrentUser, Depends(get_current_user)],
        session: Annotated[Session, Depends(get_session)],
    ):
        return InsightService(session, user, clock=lambda: NOW)

    app.dependency_overrides[get_insight_service] = insights
    receipts = OutboxDispatcher(
        factory,
        LocalTaskQueue(ReceiptProcessor(factory, storage, extractor, settings, clock=lambda: NOW)),
        clock=lambda: NOW,
    )
    inventory = InventoryDispatcher(
        factory,
        LocalInventoryTaskQueue(InventoryProcessor(factory, clock=lambda: NOW)),
        clock=lambda: NOW,
    )
    observations = InsightDispatcher(
        factory,
        LocalInsightTaskQueue(InsightProcessor(factory, clock=lambda: NOW)),
        clock=lambda: NOW,
    )
    passes = WalletDispatcher(
        factory,
        LocalWalletTaskQueue(WalletProcessor(factory, wallet_provider, clock=lambda: NOW)),
        clock=lambda: NOW,
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    host, port = listener.getsockname()
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://{host}:{port}", timeout=15, headers=ALICE) as client:
            assert (
                client.get("/api/v1/me", headers={"Authorization": "Bearer invalid"}).status_code
                == 401
            )
            owner = client.get("/api/v1/me").json()["data"]
            assert client.get("/api/v1/me").json()["data"]["id"] == owner["id"]
            assert client.get("/api/v1/me", headers=BOB).json()["data"]["id"] != owner["id"]
            binary = document()
            upload = {"file": ("synthetic.png", binary, "image/png")}
            accepted = client.post("/api/v1/receipts", files=upload)
            assert accepted.status_code == 202
            receipt_id = accepted.json()["data"]["id"]
            assert client.post("/api/v1/receipts", files=upload).status_code == 409
            assert not provider_calls["gemini"]
            assert receipts.dispatch_once() == 1
            assert receipts.dispatch_once() == 0
            assert provider_calls["gemini"] == [binary]
            receipt = client.get(f"/api/v1/receipts/{receipt_id}").json()["data"]
            assert receipt["status"] == "PROCESSED" and receipt["attempt_count"] == 1
            purchase_id = receipt["purchase_id"]
            purchase = client.get(f"/api/v1/purchases/{purchase_id}").json()["data"]
            assert purchase["grand_total"] == "11.000000"
            original = client.get(f"/api/v1/receipts/{receipt_id}/file")
            assert original.content == binary and original.headers["cache-control"] == "no-store"
            assert inventory.dispatch_once() == 1
            assert inventory.dispatch_once() == 0
            # A fresh real catalog has no eligibility flags. Explicit confirmation is required.
            assert client.get("/api/v1/inventory/lots").json()["data"] == []
            enrollment = {
                "line_item_id": purchase["line_items"][0]["id"],
                "quantity": "2",
                "unit": "each",
                "idempotency_key": str(uuid4()),
                "reason": "Explicit synthetic test confirmation",
                "expiry": {"date": "2030-09-26", "source": "USER", "confidence": "1"},
            }
            enrolled = client.post("/api/v1/inventory/lots", json=enrollment)
            assert enrolled.status_code == 201, enrolled.text
            lot = enrolled.json()["data"]
            assert (
                client.post("/api/v1/inventory/lots", json=enrollment).json()["data"]["id"]
                == lot["id"]
            )
            assert lot["quantity_remaining"] == "2.000000"
            summary = client.get("/api/v1/analytics/spending-summary", params=PERIOD).json()["data"]
            assert summary["currencies"][0]["total_spent"] == "11.000000"
            conversation = client.post("/api/v1/assistant/conversations", json={}).json()["data"][
                "id"
            ]
            turn_path = f"/api/v1/assistant/conversations/{conversation}/messages"
            submission = {
                "content": "What did I spend in September?",
                "idempotency_key": str(uuid4()),
            }
            turn = client.post(turn_path, json=submission)
            assert turn.status_code == 201, turn.text
            reply = turn.json()["data"]["assistant_message"]
            assert reply["content"] == "Your recorded spending is 11.000000 INR."
            assert reply["evidence"]["citations"][0]["value"] == "11.000000"
            assert client.post(turn_path, json=submission).status_code == 200
            assert len(provider_calls["assistant"]) == 2
            assert observations.dispatch_once() >= 2
            assert observations.dispatch_once() == 0
            insight = client.get("/api/v1/insights").json()["data"][0]
            assert insight["type"] == "INVENTORY_EXPIRY" and insight["provenance"] == "DERIVED"
            assert passes.dispatch_once() == 1
            assert passes.dispatch_once() == 0
            wallet_pass = client.get("/api/v1/wallet/passes").json()["data"][0]
            assert wallet_pass["status"] == "SYNCED" and wallet_pass["purchase_id"] == purchase_id
            pass_path = f"/api/v1/wallet/passes/{wallet_pass['id']}"
            saved = client.post(pass_path + "/add-to-wallet", json={})
            assert saved.status_code == 200
            assert (
                saved.json()["data"]["save_url"]
                == "https://pay.google.com/gp/v/save/test.only.signature"
            )
            claims = provider_calls["signing"][0]
            assert claims["payload"]["genericObjects"][0]["id"] == wallet_pass["object_id"]
            assert client.post(pass_path + "/sync", json={}).status_code == 202
            assert passes.dispatch_once() == 1
            assert {body["id"] for body in provider_calls["wallet"] if "classId" in body} == {
                wallet_pass["object_id"]
            }
            for path in [
                f"/api/v1/receipts/{receipt_id}/file",
                f"/api/v1/purchases/{purchase_id}",
                f"/api/v1/inventory/lots/{lot['id']}",
                f"/api/v1/insights/{insight['id']}",
                turn_path,
                pass_path,
            ]:
                assert client.get(path, headers=BOB).status_code == 404
            assert (
                client.post(pass_path + "/add-to-wallet", headers=BOB, json={}).status_code == 404
            )
            assert len(provider_calls["signing"]) == 1
            # Schema-valid but semantically incomplete extraction must never create a purchase.
            review_id = client.post(
                "/api/v1/receipts", files={"file": ("review.jpg", document("jpg"), "image/jpeg")}
            ).json()["data"]["id"]
            assert receipts.dispatch_once() == 1
            review = client.get(f"/api/v1/receipts/{review_id}").json()["data"]
            assert review["status"] == "NEEDS_REVIEW" and review["purchase_id"] is None
            assert receipts.dispatch_once() == 0
            assert len(client.get("/api/v1/purchases").json()["data"]) == 1
            assert "alice-token" in verified_tokens and "bob-token" in verified_tokens
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        listener.close()
        assert not thread.is_alive()
