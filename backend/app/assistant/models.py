from datetime import datetime
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_conversations_id_user"),
        CheckConstraint("title IS NULL OR length(trim(title)) > 0", name="title_nonblank"),
        CheckConstraint("next_sequence > 0", name="positive_sequence"),
        Index("ix_conversations_user_updated", "user_id", "updated_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    title: Mapped[str | None] = mapped_column(String(200))
    next_sequence: Mapped[int] = mapped_column(server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "id", "conversation_id", "user_id", name="uq_messages_id_conversation_user"
        ),
        UniqueConstraint("conversation_id", "sequence", name="uq_messages_conversation_sequence"),
        UniqueConstraint("conversation_id", "idempotency_key", name="uq_messages_conversation_key"),
        UniqueConstraint("reply_to_id", name="uq_messages_reply"),
        ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["conversations.id", "conversations.user_id"],
            name="fk_messages_conversation_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["reply_to_id", "conversation_id", "user_id"],
            ["messages.id", "messages.conversation_id", "messages.user_id"],
            name="fk_messages_reply_owner",
            ondelete="RESTRICT",
        ),
        CheckConstraint("sequence > 0 AND model_attempts >= 0", name="positive_counters"),
        CheckConstraint("role IN ('USER', 'ASSISTANT')", name="role"),
        CheckConstraint("status IN ('PROCESSING', 'COMPLETED', 'FAILED')", name="status"),
        CheckConstraint(
            "(role = 'USER' AND status = 'COMPLETED' AND reply_to_id IS NULL "
            "AND idempotency_key IS NOT NULL AND provider IS NULL AND model IS NULL "
            "AND prompt_version IS NULL AND schema_version IS NULL AND model_attempts = 0 "
            "AND evidence IS NULL AND length(content) <= 8000) OR "
            "(role = 'ASSISTANT' AND reply_to_id IS NOT NULL AND reply_to_id <> id "
            "AND idempotency_key IS NULL AND provider IS NOT NULL "
            "AND prompt_version IS NOT NULL AND schema_version IS NOT NULL)",
            name="role_fields",
        ),
        CheckConstraint(
            "(status = 'PROCESSING' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL "
            "AND lease_expires_at > created_at AND completed_at IS NULL) OR "
            "(status <> 'PROCESSING' AND lease_token IS NULL AND lease_expires_at IS NULL "
            "AND completed_at IS NOT NULL AND completed_at >= created_at)",
            name="lifecycle",
        ),
        CheckConstraint(
            "(status = 'COMPLETED' AND content IS NOT NULL AND length(trim(content)) > 0 "
            "AND length(content) <= 16000) OR (status <> 'COMPLETED' AND content IS NULL)",
            name="content_state",
        ),
        CheckConstraint(
            "(status = 'FAILED' AND failure_code IS NOT NULL AND failure_message IS NOT NULL) "
            "OR (status <> 'FAILED' AND failure_code IS NULL AND failure_message IS NULL)",
            name="failure_state",
        ),
        CheckConstraint(
            "(role = 'ASSISTANT' AND status = 'COMPLETED' AND evidence IS NOT NULL) OR "
            "((role <> 'ASSISTANT' OR status <> 'COMPLETED') AND evidence IS NULL)",
            name="evidence_state",
        ),
        Index("ix_messages_user_conversation_sequence", "user_id", "conversation_id", "sequence"),
        Index(
            "uq_messages_active_conversation",
            "conversation_id",
            unique=True,
            postgresql_where=text("status = 'PROCESSING'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID]
    conversation_id: Mapped[UUID]
    sequence: Mapped[int]
    role: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(12))
    content: Mapped[str | None] = mapped_column(Text)
    reply_to_id: Mapped[UUID | None]
    idempotency_key: Mapped[UUID | None]
    evidence: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB(none_as_null=True))
    provider: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    schema_version: Mapped[str | None] = mapped_column(String(100))
    model_attempts: Mapped[int] = mapped_column(server_default="0")
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_message: Mapped[str | None] = mapped_column(String(500))
    lease_token: Mapped[UUID | None]
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ToolExecution(Base):
    __tablename__ = "tool_executions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["message_id", "conversation_id", "user_id"],
            ["messages.id", "messages.conversation_id", "messages.user_id"],
            name="fk_tool_executions_message_owner",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("message_id", "call_id", name="uq_tool_executions_message_call"),
        CheckConstraint("status IN ('RUNNING', 'SUCCEEDED', 'FAILED')", name="status"),
        CheckConstraint("length(call_id) > 0 AND length(tool_name) > 0", name="nonempty_call"),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="request_hash"),
        CheckConstraint("octet_length(raw_arguments) <= 16384", name="arguments_size"),
        CheckConstraint(
            "result IS NULL OR octet_length(result::text) <= 131072", name="result_size"
        ),
        CheckConstraint(
            "(status = 'RUNNING' AND result IS NULL AND completed_at IS NULL "
            "AND elapsed_ms IS NULL) "
            "OR (status <> 'RUNNING' AND result IS NOT NULL AND completed_at IS NOT NULL "
            "AND completed_at >= started_at AND elapsed_ms IS NOT NULL AND elapsed_ms >= 0)",
            name="lifecycle",
        ),
        CheckConstraint(
            "result IS NULL OR (result ->> 'status' IS NOT NULL AND result ->> 'status' = status)",
            name="result_status",
        ),
        Index("ix_tool_executions_user_message", "user_id", "message_id", "started_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID]
    conversation_id: Mapped[UUID]
    message_id: Mapped[UUID]
    call_id: Mapped[str] = mapped_column(String(200))
    tool_name: Mapped[str] = mapped_column(String(100))
    raw_arguments: Mapped[str] = mapped_column(Text)
    arguments: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB(none_as_null=True))
    request_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB(none_as_null=True))
    status: Mapped[str] = mapped_column(String(12))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    elapsed_ms: Mapped[int | None]
