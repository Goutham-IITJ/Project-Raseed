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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class MarketSearch(Base):
    __tablename__ = "market_searches"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_market_searches_id_user"),
        ForeignKeyConstraint(
            ["purchase_id", "user_id"],
            ["purchases.id", "purchases.user_id"],
            name="fk_market_searches_purchase_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["line_item_id", "purchase_id"],
            ["line_items.id", "line_items.purchase_id"],
            name="fk_market_searches_line_purchase",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(line_item_id IS NOT NULL AND purchase_id IS NOT NULL) OR "
            "(line_item_id IS NULL AND purchase_id IS NULL AND product_id IS NOT NULL)",
            name="target",
        ),
        CheckConstraint(
            "status IN ('PENDING','PROCESSING','RETRY','SUCCEEDED','FAILED')", name="status"
        ),
        CheckConstraint("attempt_count BETWEEN 0 AND 3", name="attempts"),
        CheckConstraint("country ~ '^[A-Z]{2}$' AND currency ~ '^[A-Z]{3}$'", name="context"),
        CheckConstraint("fingerprint ~ '^[a-f0-9]{64}$'", name="fingerprint"),
        CheckConstraint(
            "jsonb_typeof(target) = 'object' AND octet_length(target::text) <= 8192",
            name="snapshot",
        ),
        CheckConstraint(
            "(status = 'PROCESSING' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) "
            "OR (status <> 'PROCESSING' AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name="lease",
        ),
        CheckConstraint(
            "(status IN ('SUCCEEDED','FAILED')) = (completed_at IS NOT NULL) "
            "AND (status NOT IN ('RETRY','FAILED') OR failure_code IS NOT NULL) "
            "AND (status <> 'SUCCEEDED' OR (failure_code IS NULL AND expires_at IS NOT NULL))",
            name="terminal",
        ),
        Index("ix_market_searches_owner_cache", "user_id", "fingerprint", "created_at"),
        Index(
            "ix_market_searches_active",
            "user_id",
            "fingerprint",
            unique=True,
            postgresql_where=text("status IN ('PENDING','PROCESSING','RETRY')"),
        ),
        Index(
            "ix_market_searches_ready",
            "next_attempt_at",
            "id",
            postgresql_where=text("status IN ('PENDING','PROCESSING','RETRY')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    purchase_id: Mapped[UUID | None]
    line_item_id: Mapped[UUID | None]
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    target: Mapped[dict[str, object]] = mapped_column(JSONB)
    currency: Mapped[str] = mapped_column(String(3))
    country: Mapped[str] = mapped_column(String(2))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    attempt_count: Mapped[int]
    failure_code: Mapped[str | None] = mapped_column(String(100))
    lease_token: Mapped[UUID | None]
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MarketPriceObservation(Base):
    __tablename__ = "market_price_observations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["search_id", "user_id"],
            ["market_searches.id", "market_searches.user_id"],
            name="fk_market_observations_search_owner",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("search_id", "provider", "offer_id", name="uq_market_observations_offer"),
        CheckConstraint("price >= 0 AND shipping >= 0 AND tax >= 0", name="prices"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency"),
        CheckConstraint("provenance = 'EXTERNAL'", name="provenance"),
        CheckConstraint(
            "match_status IN ('EXACT','UNCERTAIN','MISMATCH') "
            "AND match_confidence BETWEEN 0 AND 1 "
            "AND match_provenance = 'DERIVED'",
            name="matching",
        ),
        CheckConstraint(
            "observed_at <= fetched_at AND expires_at > observed_at", name="timestamps"
        ),
        CheckConstraint(
            "jsonb_typeof(offer) = 'object' AND octet_length(offer::text) <= 16384", name="offer"
        ),
        CheckConstraint(
            "length(trim(provider)) > 0 AND length(trim(offer_id)) > 0 "
            "AND length(trim(source)) > 0 AND url LIKE 'https://%'",
            name="source",
        ),
        Index("ix_market_observations_owner", "user_id", "observed_at", "id"),
        Index("ix_market_observations_product", "product_id", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    search_id: Mapped[UUID]
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    provider: Mapped[str] = mapped_column(String(40))
    offer_id: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(2048))
    merchant: Mapped[str] = mapped_column(String(500))
    location: Mapped[str | None] = mapped_column(String(500))
    currency: Mapped[str] = mapped_column(String(3))
    price: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    shipping: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    tax: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provenance: Mapped[str] = mapped_column(String(20))
    match_status: Mapped[str] = mapped_column(String(20))
    match_confidence: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    match_rule: Mapped[str] = mapped_column(String(80))
    match_provenance: Mapped[str] = mapped_column(String(20))
    # Bounded identity/pack/availability evidence; price/provenance remain relational.
    offer: Mapped[dict[str, object]] = mapped_column(JSONB)
