"""Assistant conversations and tools

Revision ID: 0006_assistant_tools
Revises: 0005_financial_analytics
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_assistant_tools"
down_revision = "0005_financial_analytics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("next_sequence", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("next_sequence > 0", name=op.f("ck_conversations_positive_sequence")),
        sa.CheckConstraint(
            "title IS NULL OR length(trim(title)) > 0", name=op.f("ck_conversations_title_nonblank")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_conversations_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
        sa.UniqueConstraint("id", "user_id", name="uq_conversations_id_user"),
    )
    op.create_index(
        "ix_conversations_user_updated",
        "conversations",
        ["user_id", "updated_at", "id"],
        unique=False,
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("reply_to_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.Uuid(), nullable=True),
        sa.Column(
            "evidence", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True
        ),
        sa.Column("provider", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=100), nullable=True),
        sa.Column("schema_version", sa.String(length=100), nullable=True),
        sa.Column("model_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_message", sa.String(length=500), nullable=True),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(role = 'ASSISTANT' AND status = 'COMPLETED' AND evidence IS NOT NULL) OR "
            "((role <> 'ASSISTANT' OR status <> 'COMPLETED') AND evidence IS NULL)",
            name=op.f("ck_messages_evidence_state"),
        ),
        sa.CheckConstraint(
            "(role = 'USER' AND status = 'COMPLETED' AND reply_to_id IS NULL "
            "AND idempotency_key IS NOT NULL AND provider IS NULL AND model IS NULL "
            "AND prompt_version IS NULL AND schema_version IS NULL AND model_attempts = 0 "
            "AND evidence IS NULL AND length(content) <= 8000) OR "
            "(role = 'ASSISTANT' AND reply_to_id IS NOT NULL AND reply_to_id <> id "
            "AND idempotency_key IS NULL AND provider IS NOT NULL "
            "AND prompt_version IS NOT NULL AND schema_version IS NOT NULL)",
            name=op.f("ck_messages_role_fields"),
        ),
        sa.CheckConstraint(
            "(status = 'COMPLETED' AND content IS NOT NULL AND length(trim(content)) > 0 "
            "AND length(content) <= 16000) OR (status <> 'COMPLETED' AND content IS NULL)",
            name=op.f("ck_messages_content_state"),
        ),
        sa.CheckConstraint(
            "(status = 'FAILED' AND failure_code IS NOT NULL AND failure_message IS NOT NULL) "
            "OR (status <> 'FAILED' AND failure_code IS NULL AND failure_message IS NULL)",
            name=op.f("ck_messages_failure_state"),
        ),
        sa.CheckConstraint(
            "(status = 'PROCESSING' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL "
            "AND lease_expires_at > created_at AND completed_at IS NULL) OR "
            "(status <> 'PROCESSING' AND lease_token IS NULL AND lease_expires_at IS NULL "
            "AND completed_at IS NOT NULL AND completed_at >= created_at)",
            name=op.f("ck_messages_lifecycle"),
        ),
        sa.CheckConstraint("role IN ('USER', 'ASSISTANT')", name=op.f("ck_messages_role")),
        sa.CheckConstraint(
            "status IN ('PROCESSING', 'COMPLETED', 'FAILED')", name=op.f("ck_messages_status")
        ),
        sa.CheckConstraint(
            "sequence > 0 AND model_attempts >= 0", name=op.f("ck_messages_positive_counters")
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["conversations.id", "conversations.user_id"],
            name="fk_messages_conversation_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reply_to_id", "conversation_id", "user_id"],
            ["messages.id", "messages.conversation_id", "messages.user_id"],
            name="fk_messages_reply_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
        sa.UniqueConstraint(
            "conversation_id", "idempotency_key", name="uq_messages_conversation_key"
        ),
        sa.UniqueConstraint(
            "conversation_id", "sequence", name="uq_messages_conversation_sequence"
        ),
        sa.UniqueConstraint(
            "id", "conversation_id", "user_id", name="uq_messages_id_conversation_user"
        ),
        sa.UniqueConstraint("reply_to_id", name="uq_messages_reply"),
    )
    op.create_index(
        "ix_messages_user_conversation_sequence",
        "messages",
        ["user_id", "conversation_id", "sequence"],
        unique=False,
    )
    op.create_index(
        "uq_messages_active_conversation",
        "messages",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PROCESSING'"),
    )
    op.create_table(
        "tool_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("call_id", sa.String(length=200), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("raw_arguments", sa.Text(), nullable=False),
        sa.Column(
            "arguments", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True
        ),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "result", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True
        ),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "(status = 'RUNNING' AND result IS NULL AND completed_at IS NULL "
            "AND elapsed_ms IS NULL) OR (status <> 'RUNNING' AND result IS NOT NULL "
            "AND completed_at IS NOT NULL AND completed_at >= started_at "
            "AND elapsed_ms IS NOT NULL AND elapsed_ms >= 0)",
            name=op.f("ck_tool_executions_lifecycle"),
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_tool_executions_request_hash")
        ),
        sa.CheckConstraint(
            "result IS NULL OR (result ->> 'status' IS NOT NULL AND result ->> 'status' = status)",
            name=op.f("ck_tool_executions_result_status"),
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'SUCCEEDED', 'FAILED')", name=op.f("ck_tool_executions_status")
        ),
        sa.CheckConstraint(
            "length(call_id) > 0 AND length(tool_name) > 0",
            name=op.f("ck_tool_executions_nonempty_call"),
        ),
        sa.CheckConstraint(
            "octet_length(raw_arguments) <= 16384", name=op.f("ck_tool_executions_arguments_size")
        ),
        sa.CheckConstraint(
            "result IS NULL OR octet_length(result::text) <= 131072",
            name=op.f("ck_tool_executions_result_size"),
        ),
        sa.ForeignKeyConstraint(
            ["message_id", "conversation_id", "user_id"],
            ["messages.id", "messages.conversation_id", "messages.user_id"],
            name="fk_tool_executions_message_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_executions")),
        sa.UniqueConstraint("message_id", "call_id", name="uq_tool_executions_message_call"),
    )
    op.create_index(
        "ix_tool_executions_user_message",
        "tool_executions",
        ["user_id", "message_id", "started_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tool_executions_user_message", table_name="tool_executions")
    op.drop_table("tool_executions")
    op.drop_index(
        "uq_messages_active_conversation",
        table_name="messages",
        postgresql_where=sa.text("status = 'PROCESSING'"),
    )
    op.drop_index("ix_messages_user_conversation_sequence", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversations_user_updated", table_name="conversations")
    op.drop_table("conversations")
