import os
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from firebase_admin import auth, credentials

from backend.app.config import ROOT, Settings
from backend.app.identity.context import VerifiedIdentity
from backend.app.main import create_app


@pytest.fixture
def root_env(monkeypatch, tmp_path):
    # Exercise the automatic loader without reading or modifying the developer's .env.
    assert Settings.model_config["env_file"] == ROOT / ".env"
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
    root = tmp_path / "repository"
    root.mkdir()
    env_file = root / ".env"
    monkeypatch.setitem(Settings.model_config, "env_file", env_file)
    return env_file


def test_startup_loads_root_firebase_settings_without_shell_exports(root_env, monkeypatch):
    key_path = root_env.parent.parent / "private keys" / "dév-firebase.json"
    root_env.write_text(
        f'FIREBASE_PROJECT_ID=local-project\nFIREBASE_ADMIN_CREDENTIALS_PATH="{key_path.as_posix()}"\n',
        encoding="utf-8",
    )
    nested = root_env.parent / "backend"
    nested.mkdir()
    (nested / ".env").write_text("FIREBASE_PROJECT_ID=wrong-project\n", encoding="utf-8")
    monkeypatch.chdir(nested)
    certificate = Mock(return_value=Mock(spec=credentials.Base))
    monkeypatch.setattr(credentials, "Certificate", certificate)
    verify = Mock(return_value={"uid": "verified-uid"})
    monkeypatch.setattr(auth, "verify_id_token", verify)

    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        certificate.assert_not_called()
        verify.assert_not_called()
        verifier = client.app.state.token_verifier
        assert verifier.verify("token") == VerifiedIdentity("verified-uid")
        assert verifier.verify("another-token") == VerifiedIdentity("verified-uid")
        certificate.assert_called_once_with(str(key_path))
        application = verify.call_args.kwargs["app"]
        assert application.project_id == "local-project"
        assert application.credential is certificate.return_value
        assert verify.call_args.kwargs["check_revoked"] is True

    # Loading settings must not change ADC configuration for other Google adapters.
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ
    assert "FIREBASE_PROJECT_ID" not in os.environ
    assert "FIREBASE_ADMIN_CREDENTIALS_PATH" not in os.environ


def test_process_environment_overrides_firebase_dotenv_values(root_env, monkeypatch):
    root_env.write_text(
        "FIREBASE_PROJECT_ID=dotenv-project\nFIREBASE_ADMIN_CREDENTIALS_PATH=/private/dotenv.json\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "runtime-project")
    monkeypatch.setenv("FIREBASE_ADMIN_CREDENTIALS_PATH", "/private/runtime.json")
    settings = Settings()
    assert settings.firebase_project_id == "runtime-project"
    assert settings.firebase_admin_credentials_path == Path("/private/runtime.json")

    monkeypatch.setenv("FIREBASE_ADMIN_CREDENTIALS_PATH", "")
    assert Settings().firebase_admin_credentials_path is None


@pytest.mark.parametrize(
    "entry", ["", "FIREBASE_ADMIN_CREDENTIALS_PATH=\n", 'FIREBASE_ADMIN_CREDENTIALS_PATH="  "\n']
)
def test_missing_or_blank_admin_path_keeps_adc(root_env, entry):
    root_env.write_text("FIREBASE_PROJECT_ID=project-id\n" + entry, encoding="utf-8")
    settings = Settings()
    assert settings.firebase_project_id == "project-id"
    assert settings.firebase_admin_credentials_path is None
