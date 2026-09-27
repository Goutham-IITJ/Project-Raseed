from uuid import uuid4

import pytest
from conftest import FakeVerifier
from fastapi.testclient import TestClient
from m7_fixtures import ALICE, BOB, purchase
from wallet_fixtures import FakeWallet, ensure, wallet_settings, worker

from backend.app.main import create_app
from backend.app.wallet.provider import WalletFailure

ROOT = "/api/v1/wallet/passes"


def app(env, fake):
    return create_app(
        wallet_settings(),
        verifier=FakeVerifier(),
        session_factory=env.factory,
        wallet_provider=fake,
    )


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", ROOT, None),
        ("POST", ROOT, {"purchase_id": str(uuid4())}),
        ("GET", ROOT + "/" + str(uuid4()), None),
        ("POST", ROOT + "/" + str(uuid4()) + "/sync", {}),
        ("POST", ROOT + "/" + str(uuid4()) + "/add-to-wallet", {}),
    ],
)
def test_all_wallet_routes_require_authentication_before_database_access(
    unauthenticated_client, method, path, body
):
    response = unauthenticated_client.request(method, path, json=body)
    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.integration
def test_owned_api_flow_from_queue_through_sync_and_signed_link(environment):
    env = environment
    item = purchase(env)
    processor, dispatcher, fake = worker(env)
    with TestClient(app(env, fake)) as client:
        response = client.post(ROOT, headers=ALICE, json={"purchase_id": str(item.id)})
        assert response.status_code == 202 and response.headers["Cache-Control"] == "no-store"
        row = response.json()["data"]
        assert row["status"] == "PENDING" and row["class_id"] is None
        assert not {"user_id", "lease_token", "lease_expires_at"} & row.keys()
        detail = ROOT + "/" + row["id"]
        assert (
            client.post(ROOT, headers=ALICE, json={"purchase_id": str(item.id)}).json()
            == response.json()
        )
        assert fake.calls == []
        assert client.post(detail + "/add-to-wallet", headers=ALICE, json={}).status_code == 409
        assert dispatcher.dispatch_once() == 1
        synced = client.get(detail, headers=ALICE)
        assert synced.status_code == 200 and synced.json()["data"]["status"] == "SYNCED"
        saved = client.post(detail + "/add-to-wallet", headers=ALICE, json={})
        assert saved.status_code == 200
        assert saved.json()["data"]["save_url"].startswith("https://pay.google.com/gp/v/save/")
        assert len(fake.links) == 1
        assert client.get(ROOT, headers=ALICE, params={"purchase_id": item.id}).json()["data"] == [
            synced.json()["data"]
        ]
        queued = client.post(detail + "/sync", headers=ALICE, json={})
        assert queued.status_code == 202 and queued.json()["data"]["status"] == "PENDING"
        assert len(fake.calls) == 1  # API only queued work.
        dispatcher.dispatch_once()
        assert len(fake.objects) == 1


@pytest.mark.integration
def test_api_cannot_read_sync_issue_or_create_another_owners_pass(environment):
    env = environment
    item = purchase(env)
    row = ensure(env, item)
    fake = FakeWallet()
    with TestClient(app(env, fake)) as client:
        for pass_id in (row.id, uuid4()):
            detail = ROOT + "/" + str(pass_id)
            for method, suffix in (("GET", ""), ("POST", "/sync"), ("POST", "/add-to-wallet")):
                response = client.request(
                    method, detail + suffix, headers=BOB, json={} if method == "POST" else None
                )
                assert response.status_code == 404
                assert response.json()["error"]["code"] == "not_found"
        assert client.post(ROOT, headers=BOB, json={"purchase_id": str(item.id)}).status_code == 404
        assert client.get(ROOT, headers=BOB, params={"purchase_id": item.id}).json() == {"data": []}
        assert not fake.calls and not fake.links


@pytest.mark.integration
@pytest.mark.parametrize(
    "code,status",
    [
        ("wallet_configuration", 503),
        ("wallet_authorization", 503),
        ("wallet_unavailable", 503),
        ("wallet_invalid_response", 502),
        ("wallet_timeout", 504),
    ],
)
def test_issuance_failure_is_safe_and_does_not_change_sync_state(environment, code, status):
    env = environment
    row = ensure(env, purchase(env))
    _, dispatcher, fake = worker(env)
    dispatcher.dispatch_once()
    fake.link_failure = WalletFailure(code)
    detail = ROOT + "/" + str(row.id)
    with TestClient(app(env, fake)) as client:
        before = client.get(detail, headers=ALICE).json()
        response = client.post(detail + "/add-to-wallet", headers=ALICE, json={})
        assert response.status_code == status
        assert response.json() == {
            "error": {"code": code, "message": "Wallet link could not be issued."}
        }
        assert client.get(detail, headers=ALICE).json() == before


@pytest.mark.integration
def test_wallet_request_validation_rejects_ownership_and_projection_overrides(environment):
    env = environment
    item = purchase(env)
    row = ensure(env, item)
    detail = ROOT + "/" + str(row.id)
    with TestClient(app(env, FakeWallet())) as client:
        for extra in ({"user_id": str(env.bob.id)}, {"class_id": "evil"}, {"status": "SYNCED"}):
            assert (
                client.post(
                    ROOT, headers=ALICE, json={"purchase_id": str(item.id), **extra}
                ).status_code
                == 422
            )
            assert client.post(detail + "/sync", headers=ALICE, json=extra).status_code == 422
            assert (
                client.post(detail + "/add-to-wallet", headers=ALICE, json=extra).status_code == 422
            )
        for params in (
            {"user_id": str(env.bob.id)},
            {"limit": 101},
            {"offset": -1},
            {"status": "BAD"},
        ):
            assert client.get(ROOT, headers=ALICE, params=params).status_code == 422
        assert client.get(detail, headers=ALICE, params={"extra": "no"}).status_code == 422
        assert client.post(detail + "/sync?user_id=bad", headers=ALICE, json={}).status_code == 422
        assert client.post(ROOT, headers=ALICE, json={"purchase_id": "bad"}).status_code == 422
