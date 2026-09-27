from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from assistant_fixtures import ScriptedModel, final
from conftest import migration_config
from m7_fixtures import NOW
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from test_insights_integration import job, stock
from test_migrations import canonical_row_sql

from backend.app.assistant.schemas import ConversationCreate, MessageCreate
from backend.app.assistant.service import AssistantService
from backend.app.database import Base
from backend.app.insights.models import Insight
from backend.app.insights.worker import InsightProcessor
from backend.app.memory.schemas import MemoryCreate
from backend.app.memory.service import MemoryService
from backend.app.purchases.models import OutboxEvent

pytestmark = pytest.mark.integration


def test_memory_insight_migration_preserves_m6_and_original_outbox_state(environment, database_url):
    env = environment
    lot = stock(env)
    assistant = AssistantService(env.factory, env.alice, ScriptedModel(final()), clock=lambda: NOW)
    conversation = assistant.create_conversation(ConversationCreate(title="Preserve M6"))
    turn = assistant.submit_message(
        conversation.id, MessageCreate(content="Hello", idempotency_key=uuid4())
    )
    with env.factory() as session:
        MemoryService(session, env.alice, clock=lambda: NOW).create(
            MemoryCreate(
                type="PREFERENCE",
                content="Vegan diet",
                topics=["food"],
                source_message_id=turn.user_message.id,
            )
        )
    task = job(env, lot_id=lot.id)
    InsightProcessor(env.factory, clock=lambda: NOW).process(task)
    with env.factory() as session:
        insight_id = session.scalar(select(Insight.id))
        assert insight_id is not None
    for changes in [{"confidence": 2}, {"source_data": []}, {"status": "FAKE"}, {"version": 0}]:
        with env.factory() as session, pytest.raises(IntegrityError), session.begin():
            row = session.get(Insight, insight_id)
            for key, value in changes.items():
                setattr(row, key, value)
            session.flush()

    tables = (
        "users",
        "user_preferences",
        "purchases",
        "line_items",
        "payments",
        "inventory_items",
        "inventory_lots",
        "inventory_events",
        "conversations",
        "messages",
        "tool_executions",
    )

    def snapshot():
        with env.database.connect() as connection:
            rows = {table: list(connection.scalars(canonical_row_sql(table))) for table in tables}
            # M7 jobs are intentionally discarded, so compare only original event kinds.
            rows["outbox_events"] = list(
                connection.scalars(
                    text(
                        "SELECT (to_jsonb(record) - ARRAY['insight_id', 'evaluation_lot_id', "
                        "'schedule_key', "
                        "'insight_processed_at', 'insight_available_at', 'insight_attempt_count', "
                        "'insight_failure_code', 'insight_failed_at', "
                        "'wallet_processed_at'])::text "
                        "FROM outbox_events record WHERE event_type IN "
                        "('PURCHASE_CREATED', 'RECEIPT_UPLOADED', 'INVENTORY_CHANGED') ORDER BY id"
                    )
                )
            )
            return rows

    before = snapshot()
    indexes = {row["name"] for row in inspect(env.database).get_indexes("memories")}
    assert "ix_memories_search" in indexes
    config = migration_config(database_url)
    command.downgrade(config, "0006_assistant_tools")
    assert not {"memories", "insights"} & set(inspect(env.database).get_table_names())
    assert snapshot() == before
    command.upgrade(config, "head")
    assert snapshot() == before
    with env.factory() as session:
        assert session.scalar(select(Insight.id)) is None
        assert session.get(OutboxEvent, task.event_id) is None
    with env.database.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
