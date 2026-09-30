from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select

from backend.app.assistant.errors import AssistantFailure
from backend.app.assistant.models import Conversation, Message, ToolExecution
from backend.app.config import Settings
from backend.app.database import Base, make_session_factory
from backend.app.identity.context import InvalidToken, VerifiedIdentity
from backend.app.identity.demo import DEMO_IDENTITY, DEMO_TOKEN, LocalDemoVerifier
from backend.app.identity.firebase import FirebaseTokenVerifier
from backend.app.identity.models import User
from backend.app.identity.service import provision_user
from backend.app.insights.models import Insight
from backend.app.inventory.models import InventoryEvent, InventoryItem, InventoryLot
from backend.app.main import create_app
from backend.app.memory.models import Memory
from backend.app.purchases.models import Purchase, Receipt
from backend.app.wallet.models import WalletPass
from backend.demo.seed import SeedConversationModel, seed_demo

HEADERS = {"Authorization": "Bearer " + DEMO_TOKEN}


def demo_settings(**overrides):
    return Settings(
        _env_file=None,
        **{
            "app_env": "development",
            "local_demo": True,
            "database_url": "postgresql+psycopg://raseed:unused@127.0.0.1:55439/raseed_local_demo",
            **overrides,
        },
    )


def test_demo_is_disabled_by_default_and_firebase_remains_the_default():
    settings = Settings(_env_file=None)
    assert settings.app_env == "production" and settings.local_demo is False
    assert isinstance(create_app(settings).state.token_verifier, FirebaseTokenVerifier)
    with pytest.raises(ValueError):
        LocalDemoVerifier(settings)


@pytest.mark.parametrize(
    "overrides",
    [
        {"app_env": "production"},
        {"app_env": "test"},
        {"database_url": "postgresql+psycopg://user:pass@database.example/demo_demo"},
        {"database_url": "postgresql+psycopg://user:pass@localhost/raseed"},
        {"storage_provider": "gcs"},
        {"cors_origins": ["https://app.example"]},
        {"cors_origins": ["http://localhost.evil.test:3000"]},
        {"cors_origins": ["http://localhost:3000/path"]},
    ],
)
def test_demo_rejects_unsafe_configuration(overrides):
    with pytest.raises(ValidationError):
        demo_settings(**overrides)


@pytest.mark.parametrize("variable", ["K_SERVICE", "GAE_ENV", "VERCEL", "WEBSITE_INSTANCE_ID"])
def test_hosted_runtimes_cannot_enable_demo(monkeypatch, variable):
    monkeypatch.setenv(variable, "deployed")
    with pytest.raises(ValidationError):
        demo_settings()


def test_unvalidated_settings_cannot_bypass_the_production_guard():
    invalid = demo_settings().model_copy(update={"app_env": "production"})
    with pytest.raises(ValidationError):
        create_app(invalid)


def test_only_one_literal_credential_can_resolve_the_demo_identity():
    verifier = LocalDemoVerifier(demo_settings())
    assert verifier.verify(DEMO_TOKEN) == DEMO_IDENTITY
    for token in ("", "alice-token", "firebase-bob", '{"uid":"admin"}', DEMO_TOKEN + ".other", "☃"):
        with pytest.raises(InvalidToken):
            verifier.verify(token)


@pytest.mark.parametrize(
    "host,peer,origin",
    [
        ("http://public.example", "127.0.0.1", None),
        ("http://localhost", "192.168.1.10", None),
        ("http://localhost", "127.0.0.1", "https://evil.example"),
    ],
)
def test_nonlocal_demo_requests_are_denied_before_database_access(host, peer, origin):
    with TestClient(create_app(demo_settings()), base_url=host, client=(peer, 1234)) as client:
        headers = {**HEADERS, **({"Origin": origin} if origin else {})}
        response = client.get("/api/v1/me", headers=headers)
        assert response.status_code == 403


def test_production_demo_credential_goes_through_firebase(monkeypatch):
    seen = []

    def reject(self, token):
        seen.append(token)
        raise InvalidToken

    monkeypatch.setattr(FirebaseTokenVerifier, "verify", reject)
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.get("/api/v1/me", headers=HEADERS).status_code == 401
    assert seen == [DEMO_TOKEN]


def counts(engine):
    with engine.connect() as connection:
        return {
            table.name: connection.scalar(select(func.count()).select_from(table))
            for table in Base.metadata.sorted_tables
        }


@pytest.mark.integration
def test_seed_is_owned_idempotent_and_all_product_reads_use_real_records(database, tmp_path):
    settings = demo_settings(local_storage_path=tmp_path / "receipts")
    result = seed_demo(database, settings)
    before = counts(database)
    assert before["purchases"] == 24
    assert before["merchants"] == before["categories"] == before["receipts"] == 4
    assert before["line_items"] == 29 and before["inventory_lots"] == 6
    assert before["memories"] == before["conversations"] == 3
    assert before["messages"] == 6 and before["wallet_passes"] == 5
    factory = make_session_factory(database)
    with factory() as session:
        user = provision_user(session, DEMO_IDENTITY)
        for model in (
            Purchase,
            Receipt,
            InventoryItem,
            InventoryLot,
            InventoryEvent,
            Insight,
            Memory,
            Conversation,
            Message,
            ToolExecution,
            WalletPass,
        ):
            assert set(session.scalars(select(model.user_id))) == {user.id}
        session.rollback()
        bob = provision_user(session, VerifiedIdentity("other-local-user"))
    app = create_app(settings, session_factory=factory)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 1234)) as client:
        assert client.get("/api/v1/me").status_code == 401
        profile = client.get("/api/v1/me", headers=HEADERS).json()["data"]
        assert (
            profile["id"] == result["user_id"]
            and profile["firebase_uid"] == DEMO_IDENTITY.firebase_uid
        )
        for path in (
            "/purchases",
            "/receipts",
            "/inventory/items",
            "/insights",
            "/memories",
            "/assistant/conversations",
            "/wallet/passes",
            "/me/preferences",
            "/analytics/spending-summary",
        ):
            response = client.get("/api/v1" + path, headers=HEADERS)
            assert response.status_code == 200, (path, response.text)
            assert response.json()["data"]
        purchase = client.get(
            "/api/v1/purchases/" + result["anchor_purchase_id"], headers=HEADERS
        ).json()["data"]
        assert purchase["grand_total"] == "800.000000"
        original = client.get(
            "/api/v1/receipts/" + purchase["receipt_id"] + "/file", headers=HEADERS
        )
        assert original.status_code == 200 and original.content.startswith(b"\x89PNG")
        assert (
            client.patch(
                "/api/v1/me/preferences", headers=HEADERS, json={"currency": "USD"}
            ).status_code
            == 200
        )
        assert (
            client.get(
                "/api/v1/purchases", headers=HEADERS, params={"user_id": str(bob.id)}
            ).status_code
            == 422
        )
        for path in (
            "/wallet/passes",
            "/market/searches",
            "/assistant/conversations/" + str(UUID(int=1)) + "/messages",
        ):
            assert client.post("/api/v1" + path, headers=HEADERS, json={}).status_code == 409
    before_repeat = counts(database)
    again = seed_demo(database, settings, as_of=date(2030, 1, 1))
    assert again == {**result, "status": "already seeded"}
    assert counts(database) == before_repeat
    with factory() as session:
        assert session.get(User, UUID(result["user_id"])).currency == "USD"
        assert set(session.scalars(select(WalletPass.status))) == {
            "PENDING",
            "SYNCED",
            "SYNCING",
            "RETRY",
            "FAILED",
        }
        assert set(session.scalars(select(Message.status))) == {"COMPLETED", "FAILED"}

    # A normal verifier resolving another identity cannot read the demo owner's records.
    class OtherVerifier:
        def verify(self, token):
            return VerifiedIdentity("other-local-user")

    with TestClient(
        create_app(Settings(_env_file=None), session_factory=factory, verifier=OtherVerifier())
    ) as client:
        assert client.get("/api/v1/purchases", headers=HEADERS).json()["data"] == []
        assert (
            client.get(
                "/api/v1/purchases/" + result["anchor_purchase_id"], headers=HEADERS
            ).status_code
            == 404
        )


@pytest.mark.integration
def test_concurrent_seeds_commit_one_dataset(database, tmp_path):
    settings = demo_settings(local_storage_path=tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: seed_demo(database, settings), range(2)))
    assert {row["status"] for row in results} == {"seeded", "already seeded"}
    assert len({row["user_id"] for row in results}) == 1
    assert counts(database)["purchases"] == 24


@pytest.mark.integration
def test_seed_failure_rolls_back_domain_records_and_its_own_artifacts(
    database, tmp_path, monkeypatch
):
    def fail(*args, **kwargs):
        raise RuntimeError("interrupted seed")

    monkeypatch.setattr(SeedConversationModel, "respond", fail)
    with pytest.raises(AssistantFailure):
        seed_demo(database, demo_settings(local_storage_path=tmp_path))
    assert counts(database)["purchases"] == counts(database)["users"] == 0
    assert not list(tmp_path.iterdir())
