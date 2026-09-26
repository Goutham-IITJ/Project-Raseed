from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint("user_id", "identity_key", name="uq_inventory_items_identity"),
        UniqueConstraint("id", "user_id", name="uq_inventory_items_id_user"),
        CheckConstraint("length(trim(name)) > 0 AND length(trim(unit)) > 0", name="text_valid"),
        Index("ix_inventory_items_user_created", "user_id", "created_at", "id"),
        Index("ix_inventory_items_product", "product_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    identity_key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(500))
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    unit: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InventoryLot(Base):
    __tablename__ = "inventory_lots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["item_id", "user_id"],
            ["inventory_items.id", "inventory_items.user_id"],
            name="fk_inventory_lots_item_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["purchase_id", "user_id"],
            ["purchases.id", "purchases.user_id"],
            name="fk_inventory_lots_purchase_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["line_item_id", "purchase_id"],
            ["line_items.id", "line_items.purchase_id"],
            name="fk_inventory_lots_line_purchase",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("line_item_id", name="uq_inventory_lots_line"),
        UniqueConstraint("id", "user_id", name="uq_inventory_lots_id_user"),
        Index("ix_inventory_lots_item", "item_id"),
        Index("ix_inventory_lots_purchase", "purchase_id"),
        Index("ix_inventory_lots_user_created", "user_id", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column()
    item_id: Mapped[UUID] = mapped_column()
    purchase_id: Mapped[UUID] = mapped_column()
    line_item_id: Mapped[UUID] = mapped_column()
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InventoryEvent(Base):
    __tablename__ = "inventory_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["lot_id", "user_id"],
            ["inventory_lots.id", "inventory_lots.user_id"],
            name="fk_inventory_events_lot_owner",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "user_id", name="uq_inventory_events_id_user"),
        UniqueConstraint("lot_id", "sequence", name="uq_inventory_events_sequence"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_inventory_events_idempotency"),
        CheckConstraint("sequence > 0", name="sequence_positive"),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="request_hash_valid"),
        CheckConstraint("length(trim(reason)) > 0", name="reason_nonempty"),
        CheckConstraint(
            "quantity_delta > '-Infinity'::numeric AND quantity_delta < 'Infinity'::numeric",
            name="delta_finite",
        ),
        CheckConstraint(
            "(event_type = 'PURCHASED' AND sequence = 1 AND quantity_delta > 0) OR "
            "(sequence > 1 AND ((event_type IN ('CONSUMED','EXPIRED','DISCARDED','RETURNED') "
            "AND quantity_delta < 0) OR (event_type = 'MANUAL_ADJUSTMENT' "
            "AND quantity_delta <> 0) OR event_type = 'CORRECTION'))",
            name="event_valid",
        ),
        CheckConstraint(
            "(actor = 'USER' AND source = 'USER' AND actor_user_id IS NOT NULL "
            "AND actor_user_id = user_id) OR (actor = 'INVENTORY_WORKER' "
            "AND source IN ('PURCHASE','SERVICE') AND actor_user_id IS NULL)",
            name="actor_valid",
        ),
        CheckConstraint(
            "(NOT expiry_changed AND expiry_date IS NULL AND expiry_source IS NULL "
            "AND expiry_confidence IS NULL) OR (expiry_changed AND "
            "event_type IN ('PURCHASED','CORRECTION') AND expiry_source IS NOT NULL AND "
            "((expiry_source = 'UNKNOWN' AND expiry_date IS NULL AND expiry_confidence IS NULL) "
            "OR (expiry_source IN ('RECEIPT','USER','PRODUCT_KNOWLEDGE','MODEL_ESTIMATE') "
            "AND expiry_date IS NOT NULL AND expiry_confidence IS NOT NULL "
            "AND expiry_confidence >= 0 AND expiry_confidence <= 1)))",
            name="expiry_valid",
        ),
        Index("ix_inventory_events_user_created", "user_id", "created_at", "id"),
        Index(
            "ix_inventory_events_expiry",
            "lot_id",
            "sequence",
            postgresql_where=text("expiry_changed"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column()
    lot_id: Mapped[UUID] = mapped_column()
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(30))
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    source: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(30))
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reason: Mapped[str] = mapped_column(String(500))
    idempotency_key: Mapped[UUID] = mapped_column()
    request_hash: Mapped[str] = mapped_column(String(64))
    expiry_changed: Mapped[bool] = mapped_column(Boolean)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    expiry_source: Mapped[str | None] = mapped_column(String(30))
    expiry_confidence: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
