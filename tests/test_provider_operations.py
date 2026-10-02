"""Operational boundaries are deterministic and never use live credentials."""

import sys
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from backend.app.config import Settings
from backend.app.identity.context import VerificationUnavailable
from backend.app.identity.firebase import FirebaseTokenVerifier
from backend.app.main import create_app
from backend.worker import __main__ as worker


@pytest.mark.parametrize("field", ["cors_origins", "wallet_origins"])
@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://*.example.test",
        "https://",
        "https://app.example.test/path",
        "https://user:secret@app.example.test",
        "https://@app.example.test",
        "https://:@app.example.test",
        "https://app.example.test?",
        "https://app.example.test#",
        "https://app.example.test:bad",
        "https://app.example.test:65536",
        "https://app.example.test:0",
        "https://app.example.test:",
        "https://app.example.test\\evil",
        "https://app.example.test\n",
        "https://app.example .test",
    ],
)
def test_origins_reject_unsafe_or_non_origin_urls(field, origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: [origin]})


@pytest.mark.parametrize("field", ["cors_origins", "wallet_origins"])
def test_remote_http_is_development_only(field):
    Settings(_env_file=None, app_env="development", **{field: ["http://app.example.test"]})
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", **{field: ["http://app.example.test"]})
    Settings(_env_file=None, **{field: ["http://localhost:3000", "https://app.example.test"]})


def test_settings_validation_hides_sensitive_inputs():
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_url="mysql://user:private-password@server/database")
    assert "private-password" not in str(error.value)


@pytest.mark.parametrize("project", ["", " ", "your-firebase-project-id", "replace-me"])
def test_firebase_placeholder_never_attempts_sdk_initialization(monkeypatch, project):
    initialize = Mock(side_effect=AssertionError("No provider access expected"))
    monkeypatch.setattr("firebase_admin.initialize_app", initialize)
    with pytest.raises(VerificationUnavailable):
        FirebaseTokenVerifier(project).verify("token")
    initialize.assert_not_called()


def test_unconfigured_readiness_fails_without_database_or_provider_calls():
    factory = Mock(side_effect=AssertionError("No DB access expected"))
    with TestClient(create_app(Settings(_env_file=None), session_factory=factory)) as client:
        assert client.get("/health").json() == {"status": "ok"}
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "not_ready"}
        assert response.headers["cache-control"] == "no-store"
    factory.assert_not_called()


def test_readiness_outage_is_safe_and_does_not_change_liveness():
    factory = Mock()
    factory.begin.side_effect = OperationalError("private SQL", {}, Exception("private password"))
    settings = Settings(_env_file=None, firebase_project_id="test-project")
    with TestClient(create_app(settings, session_factory=factory)) as client:
        response = client.get("/ready")
        assert response.status_code == 503 and response.json() == {"status": "not_ready"}
        assert client.get("/health").status_code == 200


def test_cors_preflight_allows_only_configured_origin_and_auth_headers():
    settings = Settings(_env_file=None, cors_origins=["https://app.example.test"])
    with TestClient(create_app(settings)) as client:
        headers = {
            "Origin": "https://app.example.test",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        }
        response = client.options("/api/v1/receipts", headers=headers)
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == headers["Origin"]
        headers["Origin"] = "https://untrusted.example.test"
        response = client.options("/api/v1/receipts", headers=headers)
        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers
        response = client.get("/api/v1/me", headers={"Origin": "https://app.example.test"})
        assert response.status_code == 401
        assert response.headers["access-control-allow-origin"] == "https://app.example.test"


@pytest.mark.parametrize("retry", [False, True])
def test_worker_database_errors_exit_nonzero_without_tracebacks(monkeypatch, capsys, retry):
    engine = Mock()
    monkeypatch.setattr(worker, "Settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(worker, "make_engine", Mock(return_value=engine))
    failure = OperationalError("secret SQL", {}, Exception("private credentials"))
    monkeypatch.setattr(worker.OutboxDispatcher, "dispatch_once", Mock(side_effect=failure))
    monkeypatch.setattr(worker.ReceiptProcessor, "retry", Mock(side_effect=failure))
    args = ["worker", "--once"]
    if retry:
        args += ["--retry", "11111111-1111-4111-8111-111111111111"]
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(SystemExit) as result:
        worker.main()
    assert result.value.code == 1
    output = capsys.readouterr().err
    assert "database unavailable" in output
    assert "private" not in output and "secret" not in output and "Traceback" not in output
    engine.dispose.assert_called_once()
