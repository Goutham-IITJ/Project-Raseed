import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url

from backend.app.config import Settings
from backend.app.database import make_engine, make_session_factory
from backend.app.identity.context import InvalidToken, VerifiedIdentity
from backend.app.main import create_app

ROOT = Path(__file__).resolve().parents[1]
pytest_plugins = ["m7_fixtures"]


class FakeVerifier:
    def verify(self, token: str) -> VerifiedIdentity:
        if token == "alice-token":
            return VerifiedIdentity("firebase-alice", "alice@example.com", "Alice")
        if token == "bob-token":
            return VerifiedIdentity("firebase-bob", "bob@example.com", "Bob")
        raise InvalidToken


def migration_config(url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["database_url"] = url
    return config


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a separate disposable PostgreSQL database")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+psycopg" or not (parsed.database or "").endswith("_test"):
        pytest.fail(
            "Refusing destructive tests: database must be PostgreSQL with a name ending _test"
        )
    application_url = make_url(Settings().database_url)
    if (parsed.host, parsed.port, parsed.database) == (
        application_url.host,
        application_url.port,
        application_url.database,
    ):
        pytest.fail("TEST_DATABASE_URL must not point at the application database")
    return url


@pytest.fixture(scope="session")
def migrated_engine(database_url: str) -> Iterator[Engine]:
    command.upgrade(migration_config(database_url), "head")
    engine = make_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def database(migrated_engine: Engine) -> Iterator[Engine]:
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE memories, insights, tool_executions, messages, conversations, "
                "outbox_events, inventory_events, inventory_lots, inventory_items, "
                "payments, line_items, purchases, extraction_runs, "
                "receipts, products, categories, merchants, user_preferences, users"
            )
        )
    yield migrated_engine


@pytest.fixture
def client(database: Engine) -> Iterator[TestClient]:
    app = create_app(
        Settings(firebase_project_id="test-project"),
        verifier=FakeVerifier(),
        session_factory=make_session_factory(database),
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def unauthenticated_client() -> Iterator[TestClient]:
    # Engine is lazy: rejected auth must not need a database connection.
    app = create_app(Settings(firebase_project_id="test-project"), verifier=FakeVerifier())
    with TestClient(app) as test_client:
        yield test_client
