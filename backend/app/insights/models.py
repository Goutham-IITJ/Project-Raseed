from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class Insight(Base):
    __tablename__ = "insights"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_insights_id_user"),
        UniqueConstraint("user_id", "deduplication_key", name="uq_insights_user_key"),
        CheckConstraint(
            "type IN ('SPENDING_CHANGE','UNUSUAL_PURCHASE','INVENTORY_EXPIRY')", name="type"
        ),
        CheckConstraint(
            "status IN ('ACTIVE','READ','DISMISSED','RESOLVED','EXPIRED')", name="status"
        ),
        CheckConstraint("provenance = 'DERIVED'", name="provenance"),
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="confidence"),
        CheckConstraint("version > 0", name="version"),
        CheckConstraint(
            "expires_at > evaluated_at AND evaluated_at >= created_at AND updated_at >= created_at",
            name="timestamps",
        ),
        CheckConstraint("status <> 'DISMISSED' OR dismissed_at IS NOT NULL", name="dismissal"),
        CheckConstraint("status <> 'READ' OR read_at IS NOT NULL", name="read_state"),
        CheckConstraint(
            "jsonb_typeof(source_data) = 'object' AND octet_length(source_data::text) <= 131072 "
            "AND jsonb_typeof(calculation) = 'object' AND octet_length(calculation::text) <= 8192",
            name="evidence",
        ),
        Index("ix_insights_user_status_expiry", "user_id", "status", "expires_at"),
        Index("ix_insights_user_created", "user_id", "created_at", "id"),
        Index("ix_insights_user_scope", "user_id", "scope"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    type: Mapped[str] = mapped_column(String(30))
    deduplication_key: Mapped[str] = mapped_column(String(240))
    scope: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    source_data: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    calculation: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    provenance: Mapped[str] = mapped_column(String(20), default="DERIVED")
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
