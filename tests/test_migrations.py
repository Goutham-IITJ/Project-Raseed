import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from conftest import migration_config
from sqlalchemy import func, inspect, select

from backend.app.database import Base, make_session_factory
from backend.app.identity.context import VerifiedIdentity
from backend.app.identity.models import User, UserPreference
from backend.app.identity.service import provision_user
from backend.app.purchases.models import Category

pytestmark = pytest.mark.integration


def test_migration_from_empty_database_and_model_agreement(migrated_engine, database_url):
    config = migration_config(database_url)
    command.downgrade(config, "base")
    assert set(inspect(migrated_engine).get_table_names()) <= {"alembic_version"}
    command.upgrade(config, "head")
    inspector = inspect(migrated_engine)
    assert set(inspector.get_table_names()) == {
        "alembic_version",
        "users",
        "user_preferences",
        "receipts",
        "extraction_runs",
        "merchants",
        "categories",
        "products",
        "purchases",
        "line_items",
        "payments",
        "outbox_events",
    }
    assert any(
        constraint["column_names"] == ["firebase_uid"]
        for constraint in inspector.get_unique_constraints("users")
    )
    with migrated_engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    command.upgrade(config, "head")  # Re-running the migration command is safe.


def test_upgrade_from_milestone_one_preserves_identity(migrated_engine, database_url):
    config = migration_config(database_url)
    command.downgrade(config, "0001_identity")
    with make_session_factory(migrated_engine)() as session:
        current = provision_user(session, VerifiedIdentity("migration-existing-user"))
    command.upgrade(config, "head")
    with make_session_factory(migrated_engine)() as session:
        assert session.get(User, current.id).firebase_uid == "migration-existing-user"
        assert (
            session.scalar(
                select(func.count())
                .select_from(UserPreference)
                .where(UserPreference.user_id == current.id)
            )
            == 3
        )
        assert session.scalar(select(func.count()).select_from(Category)) == 0
    columns = {
        column["name"]: column for column in inspect(migrated_engine).get_columns("purchases")
    }
    assert columns["grand_total"]["type"].precision == 20
    assert columns["grand_total"]["type"].scale == 6
    assert columns["purchased_at"]["type"].timezone is True
    assert columns["grand_total"]["nullable"] is False
    assert columns["subtotal"]["nullable"] is True
