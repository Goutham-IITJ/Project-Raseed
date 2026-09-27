import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from conftest import migration_config
from m7_fixtures import NOW, purchase
from sqlalchemy import inspect, select, text
from wallet_fixtures import worker

from backend.app.database import Base
from backend.app.memory.schemas import MemoryCreate
from backend.app.memory.service import MemoryService
from backend.app.purchases.models import OutboxEvent
from backend.app.wallet.models import WalletPass

pytestmark = pytest.mark.integration


def test_wallet_roundtrip_preserves_m7_and_rebuilds_same_external_objects(
    environment, database_url
):
    env = environment
    purchase(env)
    with env.factory() as session:
        MemoryService(session, env.alice, clock=lambda: NOW).create(
            MemoryCreate(type="PREFERENCE", content="Preserve explicit memory")
        )
    processor, dispatcher, fake = worker(env)
    assert dispatcher.dispatch_once() == 1
    with env.factory() as session:
        original_object = session.scalars(select(WalletPass)).one().object_id
    tables = [
        name
        for name in inspect(env.database).get_table_names()
        if name not in {"alembic_version", "wallet_passes"}
    ]

    def snapshot():
        with env.database.connect() as connection:
            return {
                table: list(
                    connection.scalars(
                        text(
                            "SELECT (to_jsonb(record)"
                            + (" - 'wallet_processed_at'" if table == "outbox_events" else "")
                            + f")::text FROM {table} record ORDER BY id"
                        )
                    )
                )
                for table in tables
            }

    before = snapshot()
    config = migration_config(database_url)
    command.downgrade(config, "0007_memory_insights")
    assert "wallet_passes" not in inspect(env.database).get_table_names()
    assert snapshot() == before
    command.upgrade(config, "head")
    assert snapshot() == before
    with env.factory() as session:
        assert session.scalars(select(OutboxEvent)).one().wallet_processed_at is None
    assert dispatcher.dispatch_once() == 1
    assert len(fake.objects) == 1
    with env.factory() as session:
        assert session.scalars(select(WalletPass)).one().object_id == original_object
    with env.database.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
