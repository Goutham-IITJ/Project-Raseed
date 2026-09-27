import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from conftest import migration_config
from market_fixtures import product_line, search, worker
from sqlalchemy import inspect, text
from wallet_fixtures import worker as wallet_worker

from backend.app.database import Base
from backend.app.market.models import MarketSearch

pytestmark = pytest.mark.integration


def test_market_roundtrip_preserves_canonical_wallet_and_other_subscriber_state(
    environment, database_url
):
    env = environment
    _, _, line = product_line(env)
    wallet_worker(env)[1].dispatch_once()
    row = search(env, line)
    worker(env)[1].dispatch_once()
    tables = [
        name
        for name in inspect(env.database).get_table_names()
        if name
        not in {
            "alembic_version",
            "market_searches",
            "market_price_observations",
            "outbox_events",
        }
    ]

    def snapshot():
        with env.database.connect() as connection:
            rows = {
                table: list(
                    connection.scalars(text(f"SELECT to_jsonb(r)::text FROM {table} r ORDER BY id"))
                )
                for table in tables
            }
            rows["outbox_events"] = list(
                connection.scalars(
                    text(
                        "SELECT (to_jsonb(r) - 'market_search_id')::text FROM outbox_events r "
                        "WHERE event_type <> 'MARKET_SEARCH_REQUESTED' ORDER BY id"
                    )
                )
            )
            return rows

    before = snapshot()
    config = migration_config(database_url)
    command.downgrade(config, "0008_google_wallet")
    assert "market_searches" not in inspect(env.database).get_table_names()
    assert snapshot() == before
    command.upgrade(config, "head")
    assert snapshot() == before
    with env.factory() as session:
        assert session.get(MarketSearch, row.id) is None
    with env.database.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
