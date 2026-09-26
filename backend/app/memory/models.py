from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_message_id", "source_conversation_id", "user_id"],
            ["messages.id", "messages.conversation_id", "messages.user_id"],
            name="fk_memories_source_owner",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(source_message_id IS NULL) = (source_conversation_id IS NULL)", name="source_pair"
        ),
        CheckConstraint("type IN ('PREFERENCE','GOAL','HABIT','CONSTRAINT','FACT')", name="type"),
        CheckConstraint("length(trim(content)) > 0 AND length(content) <= 1000", name="content"),
        CheckConstraint("version > 0", name="version"),
        CheckConstraint(
            "source = 'USER_EXPLICIT' AND provenance = 'OBSERVED' AND confidence = 1",
            name="explicit_source",
        ),
        CheckConstraint("expires_at IS NULL OR expires_at > updated_at", name="expiry"),
        Index("ix_memories_user_updated", "user_id", "updated_at", "id"),
        Index("ix_memories_user_expiry", "user_id", "expires_at"),
        Index(
            "ix_memories_search", text("to_tsvector('simple', search_text)"), postgresql_using="gin"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    type: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    topics: Mapped[list[str]] = mapped_column(ARRAY(String(20)))
    search_text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="USER_EXPLICIT")
    provenance: Mapped[str] = mapped_column(String(20), default="OBSERVED")
    confidence: Mapped[Decimal] = mapped_column(Numeric(7, 6), default=Decimal("1"))
    source_message_id: Mapped[UUID | None]
    source_conversation_id: Mapped[UUID | None]
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
