from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def amount_check(column: str, *, positive: bool = False) -> CheckConstraint:
    operator = ">" if positive else ">="
    return CheckConstraint(
        f"{column} {operator} 0 AND {column} < 'Infinity'::numeric", name=f"{column}_valid"
    )


class Receipt(Timestamps, Base):
    __tablename__ = "receipts"
    __table_args__ = (
        UniqueConstraint("user_id", "content_hash", name="uq_receipts_user_content_hash"),
        UniqueConstraint("id", "user_id", name="uq_receipts_id_user"),
        CheckConstraint("file_size > 0", name="file_size_positive"),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="sha256_hash"),
        CheckConstraint("length(trim(original_filename)) > 0", name="filename_nonempty"),
        CheckConstraint("length(trim(source)) > 0", name="source_nonempty"),
        CheckConstraint(
            "mime_type IN ('image/jpeg','image/png','image/webp','application/pdf')",
            name="mime_type_supported",
        ),
        CheckConstraint(
            "status IN ('PENDING_UPLOAD','UPLOADED','PROCESSING','EXTRACTED','VALIDATING',"
            "'NORMALIZED','PROCESSED','NEEDS_REVIEW','FAILED')",
            name="status_valid",
        ),
        CheckConstraint(
            "processed_at IS NULL OR (uploaded_at IS NOT NULL AND processed_at >= uploaded_at)",
            name="processing_time_valid",
        ),
        CheckConstraint(
            "status <> 'PENDING_UPLOAD' OR "
            "(storage_uri IS NULL AND uploaded_at IS NULL AND processed_at IS NULL)",
            name="pending_has_no_artifact",
        ),
        Index("ix_receipts_user_created", "user_id", "created_at", "id"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint("(lease_token IS NULL) = (lease_expires_at IS NULL)", name="lease_pair"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    storage_uri: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(BigInteger)
    content_hash: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), server_default="PENDING_UPLOAD")
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None] = mapped_column()
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, server_default="0")
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_message: Mapped[str | None] = mapped_column(String(500))
    purchase: Mapped["Purchase | None"] = relationship(viewonly=True)

    @property
    def purchase_id(self) -> UUID | None:
        return self.purchase.id if self.purchase is not None else None


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','RUNNING','SUCCEEDED','FAILED')", name="status_valid"
        ),
        CheckConstraint(
            "(status = 'PENDING' AND started_at IS NULL AND completed_at IS NULL) OR "
            "(status = 'RUNNING' AND started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status IN ('SUCCEEDED','FAILED') AND started_at IS NOT NULL "
            "AND completed_at >= started_at AND completed_at IS NOT NULL)",
            name="execution_times_valid",
        ),
        CheckConstraint(
            "length(trim(provider)) > 0 AND length(trim(model)) > 0 "
            "AND length(trim(prompt_version)) > 0 AND length(trim(schema_version)) > 0",
            name="provenance_nonempty",
        ),
        Index("ix_extraction_runs_receipt_created", "receipt_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    receipt_id: Mapped[UUID] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(100))
    schema_version: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), server_default="PENDING")
    raw_output: Mapped[dict[str, object] | None] = mapped_column(JSONB(none_as_null=True))
    normalized_output: Mapped[dict[str, object] | None] = mapped_column(JSONB(none_as_null=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Merchant(Timestamps, Base):
    __tablename__ = "merchants"
    __table_args__ = (
        CheckConstraint(
            "length(trim(canonical_name)) > 0 AND length(trim(normalized_name)) > 0",
            name="names_nonempty",
        ),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_valid"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_valid"),
        Index("ix_merchants_normalized_name", "normalized_name"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    canonical_name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(2))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))


class Category(Timestamps, Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="not_own_parent"),
        CheckConstraint("length(trim(name)) > 0", name="name_nonempty"),
        CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="slug_valid"),
        Index("ix_categories_parent", "parent_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    parent: Mapped["Category | None"] = relationship(
        remote_side="Category.id", back_populates="children"
    )
    inventory_eligible: Mapped[bool | None] = mapped_column(Boolean)
    children: Mapped[list["Category"]] = relationship(
        back_populates="parent", passive_deletes="all"
    )


class Product(Timestamps, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("length(trim(canonical_name)) > 0", name="name_nonempty"),
        Index("ix_products_category", "category_id"),
        Index("ix_products_canonical_name", "canonical_name"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    canonical_name: Mapped[str] = mapped_column(String(255))
    brand: Mapped[str | None] = mapped_column(String(100))
    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT")
    )
    unit_type: Mapped[str | None] = mapped_column(String(40))
    inventory_eligible: Mapped[bool | None] = mapped_column(Boolean)
    # SQLAlchemy reserves `metadata`; the actual PostgreSQL column keeps the domain name.
    product_metadata: Mapped[dict[str, object] | None] = mapped_column(
        "metadata", JSONB(none_as_null=True)
    )


class Purchase(Timestamps, Base):
    __tablename__ = "purchases"
    __table_args__ = (
        ForeignKeyConstraint(
            ["receipt_id", "user_id"],
            ["receipts.id", "receipts.user_id"],
            name="fk_purchases_receipt_owner",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("receipt_id", name="uq_purchases_receipt"),
        UniqueConstraint("id", "user_id", name="uq_purchases_id_user"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_valid"),
        CheckConstraint(
            "length(trim(merchant_name_raw)) > 0 AND length(trim(purchase_type)) > 0",
            name="purchase_text_nonempty",
        ),
        CheckConstraint(
            "payment_status IN ('UNKNOWN','UNPAID','PARTIALLY_PAID','PAID')",
            name="payment_status_valid",
        ),
        amount_check("subtotal"),
        amount_check("discount_total"),
        amount_check("tax_total"),
        amount_check("shipping_total"),
        amount_check("grand_total"),
        CheckConstraint(
            "subtotal IS NULL OR discount_total IS NULL OR tax_total IS NULL "
            "OR shipping_total IS NULL "
            "OR subtotal - discount_total + tax_total + shipping_total = grand_total",
            name="totals_reconcile",
        ),
        Index("ix_purchases_user_purchased", "user_id", "purchased_at", "id"),
        Index("ix_purchases_merchant", "merchant_id"),
        Index("ix_purchases_category", "category_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    receipt_id: Mapped[UUID | None] = mapped_column()
    merchant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("merchants.id", ondelete="RESTRICT")
    )
    merchant_name_raw: Mapped[str] = mapped_column(String(500))
    purchase_type: Mapped[str] = mapped_column(String(40))
    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT")
    )
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    currency: Mapped[str] = mapped_column(String(3))
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    discount_total: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    tax_total: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    shipping_total: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    grand_total: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    payment_status: Mapped[str] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)
    line_items: Mapped[list["LineItem"]] = relationship(
        back_populates="purchase",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="LineItem.id",
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="purchase",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Payment.id",
    )


class LineItem(Timestamps, Base):
    __tablename__ = "line_items"
    __table_args__ = (
        UniqueConstraint("id", "purchase_id", name="uq_line_items_id_purchase"),
        CheckConstraint("length(trim(raw_name)) > 0", name="raw_name_nonempty"),
        amount_check("quantity", positive=True),
        amount_check("unit_price"),
        amount_check("line_total"),
        Index("ix_line_items_purchase", "purchase_id"),
        Index("ix_line_items_product", "product_id"),
        Index("ix_line_items_category", "category_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    purchase_id: Mapped[UUID] = mapped_column(ForeignKey("purchases.id", ondelete="CASCADE"))
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT")
    )
    raw_name: Mapped[str] = mapped_column(String(500))
    normalized_name: Mapped[str | None] = mapped_column(String(500))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    unit: Mapped[str | None] = mapped_column(String(40))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    line_total: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    purchase: Mapped[Purchase] = relationship(back_populates="line_items")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        amount_check("amount", positive=True),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_valid"),
        CheckConstraint("last4 IS NULL OR last4 ~ '^[0-9]{4}$'", name="last4_valid"),
        CheckConstraint("length(trim(method)) > 0", name="method_nonempty"),
        Index("ix_payments_purchase", "purchase_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    purchase_id: Mapped[UUID] = mapped_column(ForeignKey("purchases.id", ondelete="CASCADE"))
    method: Mapped[str] = mapped_column(String(40))
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    currency: Mapped[str] = mapped_column(String(3))
    provider: Mapped[str | None] = mapped_column(String(100))
    reference: Mapped[str | None] = mapped_column(String(200))
    last4: Mapped[str | None] = mapped_column(String(4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    purchase: Mapped[Purchase] = relationship(back_populates="payments")


class OutboxEvent(Base):
    """Durable upload jobs and canonical purchase events."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["inventory_event_id", "user_id"],
            ["inventory_events.id", "inventory_events.user_id"],
            name="fk_outbox_events_inventory_owner",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("inventory_event_id", name="uq_outbox_events_inventory_event"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        ForeignKeyConstraint(
            ["purchase_id", "user_id"],
            ["purchases.id", "purchases.user_id"],
            name="fk_outbox_events_purchase_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["receipt_id", "user_id"],
            ["receipts.id", "receipts.user_id"],
            name="fk_outbox_events_receipt_owner",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("purchase_id", "event_type", name="uq_outbox_events_purchase_type"),
        UniqueConstraint("receipt_id", "event_type", name="uq_outbox_events_receipt_type"),
        CheckConstraint(
            "(event_type = 'PURCHASE_CREATED' AND purchase_id IS NOT NULL "
            "AND receipt_id IS NULL AND inventory_event_id IS NULL) "
            "OR (event_type = 'RECEIPT_UPLOADED' AND receipt_id IS NOT NULL "
            "AND purchase_id IS NULL AND inventory_event_id IS NULL) "
            "OR (event_type = 'INVENTORY_CHANGED' AND inventory_event_id IS NOT NULL "
            "AND purchase_id IS NULL AND receipt_id IS NULL)",
            name="event_type_supported",
        ),
        Index(
            "ix_outbox_events_pending", "created_at", postgresql_where=text("published_at IS NULL")
        ),
        Index("ix_outbox_events_user", "user_id"),
        Index(
            "ix_outbox_events_inventory_ready",
            "available_at",
            "id",
            postgresql_where=text(
                "published_at IS NULL AND failed_at IS NULL AND event_type = 'PURCHASE_CREATED'"
            ),
        ),
        Index(
            "ix_outbox_events_available",
            "available_at",
            "id",
            postgresql_where=text("published_at IS NULL AND event_type = 'RECEIPT_UPLOADED'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column()
    purchase_id: Mapped[UUID | None] = mapped_column()
    receipt_id: Mapped[UUID | None] = mapped_column()
    inventory_event_id: Mapped[UUID | None] = mapped_column()
    attempt_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
