from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from firebase_admin import auth
from firebase_admin.exceptions import UnavailableError
from google.auth.exceptions import DefaultCredentialsError

from backend.app.identity.context import InvalidToken, VerificationUnavailable, VerifiedIdentity
from backend.app.identity.firebase import FirebaseTokenVerifier


@pytest.mark.parametrize(
    "header", [None, "", "Basic abc", "Bearer", "Bearer ", "Bearer a b", "Bearer invalid"]
)
def test_missing_malformed_invalid_token_is_401(unauthenticated_client: TestClient, header):
    headers = {} if header is None else {"Authorization": header}
    response = unauthenticated_client.get("/api/v1/me", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "unauthorized"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/v1/me/preferences"),
        ("patch", "/api/v1/me/preferences"),
    ],
)
def test_preferences_require_authentication(unauthenticated_client, method, path):
    response = unauthenticated_client.request(method, path)
    assert response.status_code == 401


def test_health_is_only_liveness(unauthenticated_client):
    assert unauthenticated_client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/v1/receipts"),
        ("GET", "/api/v1/receipts"),
        ("GET", "/api/v1/receipts/b9f9d254-dcef-427b-8efb-4ba36eb324ec"),
        ("GET", "/api/v1/purchases"),
        ("GET", "/api/v1/purchases/b9f9d254-dcef-427b-8efb-4ba36eb324ec"),
    ],
)
def test_canonical_endpoints_require_authentication(unauthenticated_client, method, path):
    response = unauthenticated_client.request(method, path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_firebase_adapter_delegates_real_verification(monkeypatch):
    verifier = FirebaseTokenVerifier("project-id")
    application = object()
    monkeypatch.setattr(verifier, "_get_app", lambda: application)
    verify = Mock(return_value={"uid": "verified-uid", "email": "a@example.com", "name": "Alice"})
    monkeypatch.setattr(auth, "verify_id_token", verify)
    result = verifier.verify("opaque-token")
    assert result == VerifiedIdentity("verified-uid", "a@example.com", "Alice")
    verify.assert_called_once_with("opaque-token", app=application, check_revoked=True)


@pytest.mark.parametrize(
    "error",
    [
        auth.InvalidIdTokenError("invalid"),
        auth.ExpiredIdTokenError("expired", cause=None),
        auth.RevokedIdTokenError("revoked"),
        auth.UserDisabledError("disabled"),
        auth.UserNotFoundError("deleted user"),
    ],
)
def test_firebase_adapter_rejects_untrusted_tokens(monkeypatch, error):
    verifier = FirebaseTokenVerifier("project-id")
    monkeypatch.setattr(verifier, "_get_app", lambda: object())
    monkeypatch.setattr(auth, "verify_id_token", Mock(side_effect=error))
    with pytest.raises(InvalidToken):
        verifier.verify("untrusted")


@pytest.mark.parametrize("uid", [None, "", " ", 123, "x" * 129])
def test_firebase_adapter_requires_verified_uid(monkeypatch, uid):
    verifier = FirebaseTokenVerifier("project-id")
    monkeypatch.setattr(verifier, "_get_app", lambda: object())
    monkeypatch.setattr(auth, "verify_id_token", Mock(return_value={"uid": uid}))
    with pytest.raises(InvalidToken):
        verifier.verify("token")


@pytest.mark.parametrize("error", [DefaultCredentialsError("no ADC"), UnavailableError("offline")])
def test_infrastructure_failure_is_not_an_invalid_identity(monkeypatch, error):
    verifier = FirebaseTokenVerifier("project-id")
    monkeypatch.setattr(verifier, "_get_app", Mock(side_effect=error))
    with pytest.raises(VerificationUnavailable):
        verifier.verify("token")


def test_emulator_cannot_enable_authentication_bypass(monkeypatch):
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "localhost:9099")
    with pytest.raises(VerificationUnavailable):
        FirebaseTokenVerifier("project-id").verify("emulator-token")


def test_missing_project_fails_closed():
    with pytest.raises(VerificationUnavailable):
        FirebaseTokenVerifier("").verify("token")


def test_verifier_outage_is_503_without_details(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(
        unauthenticated_client.app.state.token_verifier,
        "verify",
        Mock(side_effect=VerificationUnavailable("private configuration")),
    )
    response = unauthenticated_client.get("/api/v1/me", headers={"Authorization": "Bearer token"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "authentication_unavailable"
    assert "private" not in response.text
