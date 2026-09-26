"""memory_insights

Revision ID: 0007_memory_insights
Revises: 0006_assistant_tools
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_memory_insights"
down_revision = "0006_assistant_tools"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # M7 adds independent insight delivery; existing subscriber state is preserved.
    op.create_table(
        "insights",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("deduplication_key", sa.String(length=240), nullable=False),
        sa.Column("scope", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("calculation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provenance", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=7, scale=6), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "jsonb_typeof(source_data) = 'object' AND octet_length(source_data::text) <= 131072 "
            "AND jsonb_typeof(calculation) = 'object' AND octet_length(calculation::text) <= 8192",
            name=op.f("ck_insights_evidence"),
        ),
        sa.CheckConstraint("provenance = 'DERIVED'", name=op.f("ck_insights_provenance")),
        sa.CheckConstraint(
            "status <> 'DISMISSED' OR dismissed_at IS NOT NULL", name=op.f("ck_insights_dismissal")
        ),
        sa.CheckConstraint(
            "status <> 'READ' OR read_at IS NOT NULL", name=op.f("ck_insights_read_state")
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','READ','DISMISSED','RESOLVED','EXPIRED')",
            name=op.f("ck_insights_status"),
        ),
        sa.CheckConstraint(
            "type IN ('SPENDING_CHANGE','UNUSUAL_PURCHASE','INVENTORY_EXPIRY')",
            name=op.f("ck_insights_type"),
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1", name=op.f("ck_insights_confidence")
        ),
        sa.CheckConstraint(
            "expires_at > evaluated_at AND evaluated_at >= created_at AND updated_at >= created_at",
            name=op.f("ck_insights_timestamps"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_insights_version")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_insights_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_insights")),
        sa.UniqueConstraint("id", "user_id", name="uq_insights_id_user"),
        sa.UniqueConstraint("user_id", "deduplication_key", name="uq_insights_user_key"),
    )
    op.create_index(
        "ix_insights_user_created", "insights", ["user_id", "created_at", "id"], unique=False
    )
    op.create_index("ix_insights_user_scope", "insights", ["user_id", "scope"], unique=False)
    op.create_index(
        "ix_insights_user_status_expiry",
        "insights",
        ["user_id", "status", "expires_at"],
        unique=False,
    )
    op.create_table(
        "memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("topics", postgresql.ARRAY(sa.String(length=20)), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("provenance", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=7, scale=6), nullable=False),
        sa.Column("source_message_id", sa.Uuid(), nullable=True),
        sa.Column("source_conversation_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source = 'USER_EXPLICIT' AND provenance = 'OBSERVED' AND confidence = 1",
            name=op.f("ck_memories_explicit_source"),
        ),
        sa.CheckConstraint(
            "type IN ('PREFERENCE','GOAL','HABIT','CONSTRAINT','FACT')",
            name=op.f("ck_memories_type"),
        ),
        sa.CheckConstraint(
            "(source_message_id IS NULL) = (source_conversation_id IS NULL)",
            name=op.f("ck_memories_source_pair"),
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > updated_at", name=op.f("ck_memories_expiry")
        ),
        sa.CheckConstraint(
            "length(trim(content)) > 0 AND length(content) <= 1000",
            name=op.f("ck_memories_content"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_memories_version")),
        sa.ForeignKeyConstraint(
            ["source_message_id", "source_conversation_id", "user_id"],
            ["messages.id", "messages.conversation_id", "messages.user_id"],
            name="fk_memories_source_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_memories_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memories")),
    )
    op.create_index("ix_memories_user_expiry", "memories", ["user_id", "expires_at"], unique=False)
    op.create_index(
        "ix_memories_user_updated", "memories", ["user_id", "updated_at", "id"], unique=False
    )
    op.create_index(
        "ix_memories_search",
        "memories",
        [sa.text("to_tsvector('simple', search_text)")],
        postgresql_using="gin",
    )
    op.add_column("outbox_events", sa.Column("insight_id", sa.Uuid(), nullable=True))
    op.add_column("outbox_events", sa.Column("evaluation_lot_id", sa.Uuid(), nullable=True))
    op.add_column("outbox_events", sa.Column("schedule_key", sa.String(length=240), nullable=True))
    op.add_column(
        "outbox_events",
        sa.Column("insight_processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "outbox_events",
        sa.Column(
            "insight_available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "outbox_events",
        sa.Column(
            "insight_attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
    )
    op.add_column(
        "outbox_events", sa.Column("insight_failure_code", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "outbox_events", sa.Column("insight_failed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_outbox_events_insight_ready",
        "outbox_events",
        ["insight_available_at", "id"],
        unique=False,
        postgresql_where=sa.text(
            "insight_processed_at IS NULL AND insight_failed_at IS NULL "
            "AND event_type IN ('PURCHASE_CREATED', 'INVENTORY_CHANGED', "
            "'INSIGHT_EVALUATION_REQUESTED')"
        ),
    )
    op.create_unique_constraint("uq_outbox_events_insight", "outbox_events", ["insight_id"])
    op.create_unique_constraint(
        "uq_outbox_events_user_schedule", "outbox_events", ["user_id", "schedule_key"]
    )
    op.create_foreign_key(
        "fk_outbox_events_user", "outbox_events", "users", ["user_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_foreign_key(
        "fk_outbox_events_insight_owner",
        "outbox_events",
        "insights",
        ["insight_id", "user_id"],
        ["id", "user_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_outbox_events_evaluation_lot_owner",
        "outbox_events",
        "inventory_lots",
        ["evaluation_lot_id", "user_id"],
        ["id", "user_id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        op.f("ck_outbox_events_event_type_supported"), "outbox_events", type_="check"
    )
    op.create_check_constraint(
        "event_type_supported",
        "outbox_events",
        "((event_type = 'PURCHASE_CREATED' AND purchase_id IS NOT NULL "
        "AND receipt_id IS NULL AND inventory_event_id IS NULL) "
        "OR (event_type = 'RECEIPT_UPLOADED' AND receipt_id IS NOT NULL "
        "AND purchase_id IS NULL AND inventory_event_id IS NULL) "
        "OR (event_type = 'INVENTORY_CHANGED' AND inventory_event_id IS NOT NULL "
        "AND purchase_id IS NULL AND receipt_id IS NULL)) "
        "AND insight_id IS NULL AND evaluation_lot_id IS NULL AND schedule_key IS NULL "
        "OR (event_type = 'INSIGHT_CREATED' AND insight_id IS NOT NULL "
        "AND purchase_id IS NULL AND receipt_id IS NULL AND inventory_event_id IS NULL "
        "AND evaluation_lot_id IS NULL AND schedule_key IS NULL) "
        "OR (event_type = 'INSIGHT_EVALUATION_REQUESTED' AND schedule_key IS NOT NULL "
        "AND length(schedule_key) > 0 AND purchase_id IS NULL AND receipt_id IS NULL "
        "AND inventory_event_id IS NULL AND insight_id IS NULL)",
    )
    op.create_check_constraint(
        "insight_attempt_count", "outbox_events", "insight_attempt_count >= 0"
    )
    op.execute(
        "UPDATE outbox_events SET insight_processed_at = now() "
        "WHERE event_type IN ('PURCHASE_CREATED', 'INVENTORY_CHANGED')"
    )


def downgrade() -> None:
    # Delete only M7 events before removing their foreign keys and supported kinds.
    op.execute(
        "DELETE FROM outbox_events "
        "WHERE event_type IN ('INSIGHT_CREATED', 'INSIGHT_EVALUATION_REQUESTED')"
    )
    op.drop_constraint(
        op.f("ck_outbox_events_event_type_supported"), "outbox_events", type_="check"
    )
    op.create_check_constraint(
        "event_type_supported",
        "outbox_events",
        "(event_type = 'PURCHASE_CREATED' AND purchase_id IS NOT NULL "
        "AND receipt_id IS NULL AND inventory_event_id IS NULL) "
        "OR (event_type = 'RECEIPT_UPLOADED' AND receipt_id IS NOT NULL "
        "AND purchase_id IS NULL AND inventory_event_id IS NULL) "
        "OR (event_type = 'INVENTORY_CHANGED' AND inventory_event_id IS NOT NULL "
        "AND purchase_id IS NULL AND receipt_id IS NULL)",
    )
    op.drop_constraint(
        op.f("ck_outbox_events_insight_attempt_count"), "outbox_events", type_="check"
    )
    op.drop_constraint("fk_outbox_events_evaluation_lot_owner", "outbox_events", type_="foreignkey")
    op.drop_constraint("fk_outbox_events_insight_owner", "outbox_events", type_="foreignkey")
    op.drop_constraint("fk_outbox_events_user", "outbox_events", type_="foreignkey")
    op.drop_constraint("uq_outbox_events_user_schedule", "outbox_events", type_="unique")
    op.drop_constraint("uq_outbox_events_insight", "outbox_events", type_="unique")
    op.drop_index(
        "ix_outbox_events_insight_ready",
        table_name="outbox_events",
        postgresql_where=sa.text(
            "insight_processed_at IS NULL AND insight_failed_at IS NULL "
            "AND event_type IN ('PURCHASE_CREATED', 'INVENTORY_CHANGED', "
            "'INSIGHT_EVALUATION_REQUESTED')"
        ),
    )
    op.drop_column("outbox_events", "insight_failed_at")
    op.drop_column("outbox_events", "insight_failure_code")
    op.drop_column("outbox_events", "insight_attempt_count")
    op.drop_column("outbox_events", "insight_available_at")
    op.drop_column("outbox_events", "insight_processed_at")
    op.drop_column("outbox_events", "schedule_key")
    op.drop_column("outbox_events", "evaluation_lot_id")
    op.drop_column("outbox_events", "insight_id")
    op.drop_index("ix_memories_user_updated", table_name="memories")
    op.drop_index("ix_memories_user_expiry", table_name="memories")
    op.drop_index("ix_memories_search", table_name="memories")
    op.drop_table("memories")
    op.drop_index("ix_insights_user_status_expiry", table_name="insights")
    op.drop_index("ix_insights_user_scope", table_name="insights")
    op.drop_index("ix_insights_user_created", table_name="insights")
    op.drop_table("insights")
