from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class WalletPass(Base):
    __tablename__ = "wallet_passes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["purchase_id", "user_id"],
            ["purchases.id", "purchases.user_id"],
            name="fk_wallet_passes_purchase_owner",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("purchase_id", "provider", "pass_type", name="uq_wallet_passes_purchase"),
        UniqueConstraint("provider", "object_id", name="uq_wallet_passes_object"),
        CheckConstraint("provider = 'GOOGLE' AND pass_type = 'GENERIC'", name="provider_type"),
        CheckConstraint("status IN ('PENDING','SYNCING','RETRY','SYNCED','FAILED')", name="status"),
        CheckConstraint("attempt_count >= 0 AND attempt_count <= 3", name="attempts"),
        CheckConstraint(
            "(class_id IS NULL AND object_id IS NULL) OR "
            "(class_id IS NOT NULL AND object_id IS NOT NULL "
            "AND class_id ~ '^[0-9]+[.][A-Za-z0-9_-]+$' "
            "AND object_id ~ '^[0-9]+[.][A-Za-z0-9_-]+$')",
            name="identifiers",
        ),
        CheckConstraint(
            "(status = 'SYNCING' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) "
            "OR (status <> 'SYNCING' AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name="lease",
        ),
        CheckConstraint(
            "status <> 'SYNCED' OR (synced_at IS NOT NULL AND object_id IS NOT NULL "
            "AND last_error_code IS NULL)",
            name="success",
        ),
        CheckConstraint(
            "(last_error_code IS NULL) = (last_error_at IS NULL) "
            "AND (status NOT IN ('RETRY','FAILED') OR last_error_code IS NOT NULL)",
            name="error",
        ),
        Index("ix_wallet_passes_user_created", "user_id", "created_at", "id"),
        Index(
            "ix_wallet_passes_ready",
            "next_attempt_at",
            "id",
            postgresql_where=text("status IN ('PENDING','RETRY','SYNCING')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    purchase_id: Mapped[UUID]
    provider: Mapped[str] = mapped_column(String(20))
    pass_type: Mapped[str] = mapped_column(String(20))
    class_id: Mapped[str | None] = mapped_column(String(200))
    object_id: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20))
    attempt_count: Mapped[int]
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None]
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
