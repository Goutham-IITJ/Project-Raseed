import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from conftest import migration_config
from sqlalchemy import inspect

from backend.app.database import Base

pytestmark = pytest.mark.integration


def test_migration_from_empty_database_and_model_agreement(migrated_engine, database_url):
    config = migration_config(database_url)
    command.downgrade(config, "base")
    assert set(inspect(migrated_engine).get_table_names()) <= {"alembic_version"}
    command.upgrade(config, "head")
    inspector = inspect(migrated_engine)
    assert set(inspector.get_table_names()) == {"alembic_version", "users", "user_preferences"}
    assert any(
        constraint["column_names"] == ["firebase_uid"]
        for constraint in inspector.get_unique_constraints("users")
    )
    with migrated_engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    command.upgrade(config, "head")  # Re-running the migration command is safe.
