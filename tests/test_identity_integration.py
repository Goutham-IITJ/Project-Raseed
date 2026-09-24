from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID

import pytest
from sqlalchemy import func, select

from backend.app.database import make_session_factory
from backend.app.identity.context import CurrentUser, VerifiedIdentity
from backend.app.identity.models import User, UserPreference
from backend.app.identity.schemas import PreferencePatch
from backend.app.identity.service import UserService, provision_user

pytestmark = pytest.mark.integration
ALICE = {"Authorization": "Bearer alice-token"}
BOB = {"Authorization": "Bearer bob-token"}


def test_first_login_provisions_internal_user_and_preferences(client, database):
    response = client.get("/api/v1/me", headers=ALICE)
    assert response.status_code == 200
    user = response.json()["data"]
    assert UUID(user["id"])
    assert user["firebase_uid"] == "firebase-alice"
    assert user["email"] == "alice@example.com"
    assert user["display_name"] == "Alice"
    assert user["currency"] == "INR"
    assert user["timezone"] == "Asia/Kolkata"
    assert user["locale"] == "en-IN"
    assert user["created_at"] and user["updated_at"]
    with make_session_factory(database)() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 1
        assert session.scalar(select(func.count()).select_from(UserPreference)) == 3


def test_valid_identity_becomes_internal_current_user(database):
    with make_session_factory(database)() as session:
        current = provision_user(session, VerifiedIdentity("verified-uid"))
        assert isinstance(current, CurrentUser)
        assert isinstance(current.id, UUID)
        assert current.firebase_uid == "verified-uid"
        assert UserService(session, current).get_user().id == current.id


def test_repeated_login_does_not_duplicate_or_reset_preferences(client, database):
    first = client.get("/api/v1/me", headers=ALICE).json()["data"]
    client.patch("/api/v1/me/preferences", headers=ALICE, json={"currency": "USD"})
    second = client.get("/api/v1/me", headers=ALICE).json()["data"]
    assert first["id"] == second["id"]
    assert second["currency"] == "USD"
    with make_session_factory(database)() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 1
        assert session.scalar(select(func.count()).select_from(UserPreference)) == 3


def test_preferences_persist_and_profile_projection_matches(client):
    changes = {"currency": "EUR", "timezone": "Europe/Paris", "locale": "fr-FR"}
    patch = client.patch("/api/v1/me/preferences", headers=ALICE, json=changes)
    assert patch.status_code == 200
    assert patch.json()["data"] == changes
    assert client.get("/api/v1/me/preferences", headers=ALICE).json()["data"] == changes
    user = client.get("/api/v1/me", headers=ALICE).json()["data"]
    assert {key: user[key] for key in changes} == changes
    partial = client.patch("/api/v1/me/preferences", headers=ALICE, json={"currency": "GBP"})
    assert partial.json()["data"] == {**changes, "currency": "GBP"}


@pytest.mark.parametrize("selector", ["user_id", "firebase_uid", "email"])
def test_preference_update_cannot_target_another_user(client, selector):
    bob = client.get("/api/v1/me", headers=BOB).json()["data"]
    target = bob["id"] if selector == "user_id" else bob[selector]
    response = client.patch(
        "/api/v1/me/preferences", headers=ALICE, json={"currency": "USD", selector: target}
    )
    assert response.status_code == 422
    response = client.patch(
        "/api/v1/me/preferences", headers=ALICE, params={selector: target}, json={"currency": "USD"}
    )
    assert response.status_code == 422
    assert client.get("/api/v1/me/preferences", headers=BOB).json()["data"]["currency"] == "INR"
    assert client.get("/api/v1/me/preferences", headers=ALICE).json()["data"]["currency"] == "INR"


def test_each_user_reads_and_updates_only_their_profile(client):
    client.patch("/api/v1/me/preferences", headers=ALICE, json={"currency": "USD"})
    client.patch("/api/v1/me/preferences", headers=BOB, json={"currency": "EUR"})
    alice = client.get("/api/v1/me", headers=ALICE).json()["data"]
    bob = client.get("/api/v1/me", headers=BOB).json()["data"]
    assert alice["id"] != bob["id"]
    assert alice["currency"] == "USD"
    assert bob["currency"] == "EUR"
    assert client.get("/api/v1/me", headers=ALICE, params={"user_id": bob["id"]}).status_code == 422


def test_concurrent_first_requests_provision_exactly_once(database):
    factory = make_session_factory(database)
    barrier = Barrier(8)

    def login(_):
        with factory() as session:
            barrier.wait(timeout=15)
            return provision_user(session, VerifiedIdentity("concurrent-uid")).id

    with ThreadPoolExecutor(max_workers=8) as executor:
        identifiers = list(executor.map(login, range(8)))
    assert len(set(identifiers)) == 1
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 1
        assert session.scalar(select(func.count()).select_from(UserPreference)) == 3


def test_concurrent_partial_updates_preserve_unrelated_fields(database):
    factory = make_session_factory(database)
    with factory() as session:
        current = provision_user(session, VerifiedIdentity("concurrent-preferences"))
    barrier = Barrier(3)
    changes = [{"currency": "USD"}, {"timezone": "America/New_York"}, {"locale": "en-US"}]

    def update(change):
        with factory() as session:
            barrier.wait(timeout=15)
            UserService(session, current).patch_preferences(PreferencePatch.model_validate(change))

    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(update, changes))
    with factory() as session:
        service = UserService(session, current)
        expected = {key: value for change in changes for key, value in change.items()}
        assert service.get_preferences().model_dump() == expected
        user = service.get_user()
        assert {key: getattr(user, key) for key in expected} == expected


def test_profile_and_preferences_roll_back_together(database, monkeypatch):
    factory = make_session_factory(database)
    with factory() as session:
        current = provision_user(session, VerifiedIdentity("rollback-uid"))
        service = UserService(session, current)
        monkeypatch.setattr(
            service._preferences, "get", lambda: (_ for _ in ()).throw(RuntimeError())
        )
        with pytest.raises(RuntimeError):
            service.patch_preferences(PreferencePatch(currency="USD"))
    with factory() as session:
        service = UserService(session, current)
        assert service.get_preferences().currency == "INR"
        assert service.get_user().currency == "INR"
