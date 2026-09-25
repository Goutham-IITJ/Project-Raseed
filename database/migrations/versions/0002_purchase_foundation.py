"""canonical receipt and purchase foundation

Revision ID: 0002_purchase_foundation
Revises: 0001_identity
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_purchase_foundation"
down_revision = "0001_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Shared catalogs precede user-owned aggregates; ownership FKs are explicit.
    op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f("ck_categories_slug_valid")
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_categories_name_nonempty")),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name=op.f("ck_categories_not_own_parent")
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["categories.id"],
            name=op.f("fk_categories_parent_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint("slug", name=op.f("uq_categories_slug")),
    )
    op.create_index("ix_categories_parent", "categories", ["parent_id"], unique=False)
    op.create_table(
        "merchants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True),
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
        sa.CheckConstraint("latitude BETWEEN -90 AND 90", name=op.f("ck_merchants_latitude_valid")),
        sa.CheckConstraint(
            "length(trim(canonical_name)) > 0 AND length(trim(normalized_name)) > 0",
            name=op.f("ck_merchants_names_nonempty"),
        ),
        sa.CheckConstraint(
            "longitude BETWEEN -180 AND 180", name=op.f("ck_merchants_longitude_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_merchants")),
    )
    op.create_index("ix_merchants_normalized_name", "merchants", ["normalized_name"], unique=False)
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("brand", sa.String(length=100), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("unit_type", sa.String(length=40), nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True
        ),
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
        sa.CheckConstraint(
            "length(trim(canonical_name)) > 0", name=op.f("ck_products_name_nonempty")
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_products_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
    )
    op.create_index("ix_products_canonical_name", "products", ["canonical_name"], unique=False)
    op.create_index("ix_products_category", "products", ["category_id"], unique=False)
    op.create_table(
        "receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDING_UPLOAD", nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_receipts_sha256_hash")),
        sa.CheckConstraint(
            "mime_type IN ('image/jpeg','image/png','image/webp','application/pdf')",
            name=op.f("ck_receipts_mime_type_supported"),
        ),
        sa.CheckConstraint(
            "status <> 'PENDING_UPLOAD' OR (storage_uri IS NULL "
            "AND uploaded_at IS NULL AND processed_at IS NULL)",
            name=op.f("ck_receipts_pending_has_no_artifact"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING_UPLOAD','UPLOADED','PROCESSING','EXTRACTED','VALIDATING',"
            "'NORMALIZED','PROCESSED','NEEDS_REVIEW','FAILED')",
            name=op.f("ck_receipts_status_valid"),
        ),
        sa.CheckConstraint("file_size > 0", name=op.f("ck_receipts_file_size_positive")),
        sa.CheckConstraint(
            "length(trim(original_filename)) > 0", name=op.f("ck_receipts_filename_nonempty")
        ),
        sa.CheckConstraint("length(trim(source)) > 0", name=op.f("ck_receipts_source_nonempty")),
        sa.CheckConstraint(
            "processed_at IS NULL OR (uploaded_at IS NOT NULL AND processed_at >= uploaded_at)",
            name=op.f("ck_receipts_processing_time_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_receipts_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_receipts")),
        sa.UniqueConstraint("id", "user_id", name="uq_receipts_id_user"),
        sa.UniqueConstraint("user_id", "content_hash", name="uq_receipts_user_content_hash"),
    )
    op.create_index(
        "ix_receipts_user_created", "receipts", ["user_id", "created_at", "id"], unique=False
    )
    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("receipt_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("schema_version", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column(
            "raw_output", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "normalized_output",
            postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND started_at IS NULL AND completed_at IS NULL) "
            "OR (status = 'RUNNING' AND started_at IS NOT NULL AND completed_at IS NULL) "
            "OR (status IN ('SUCCEEDED','FAILED') AND started_at IS NOT NULL "
            "AND completed_at >= started_at AND completed_at IS NOT NULL)",
            name=op.f("ck_extraction_runs_execution_times_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','RUNNING','SUCCEEDED','FAILED')",
            name=op.f("ck_extraction_runs_status_valid"),
        ),
        sa.CheckConstraint(
            "length(trim(provider)) > 0 AND length(trim(model)) > 0 "
            "AND length(trim(prompt_version)) > 0 AND length(trim(schema_version)) > 0",
            name=op.f("ck_extraction_runs_provenance_nonempty"),
        ),
        sa.ForeignKeyConstraint(
            ["receipt_id"],
            ["receipts.id"],
            name=op.f("fk_extraction_runs_receipt_id_receipts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extraction_runs")),
    )
    op.create_index(
        "ix_extraction_runs_receipt_created",
        "extraction_runs",
        ["receipt_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "purchases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("receipt_id", sa.Uuid(), nullable=True),
        sa.Column("merchant_id", sa.Uuid(), nullable=True),
        sa.Column("merchant_name_raw", sa.String(length=500), nullable=False),
        sa.Column("purchase_type", sa.String(length=40), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("discount_total", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("tax_total", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("shipping_total", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("grand_total", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("payment_status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_purchases_currency_valid")),
        sa.CheckConstraint(
            "discount_total >= 0 AND discount_total < 'Infinity'::numeric",
            name=op.f("ck_purchases_discount_total_valid"),
        ),
        sa.CheckConstraint(
            "grand_total >= 0 AND grand_total < 'Infinity'::numeric",
            name=op.f("ck_purchases_grand_total_valid"),
        ),
        sa.CheckConstraint(
            "payment_status IN ('UNKNOWN','UNPAID','PARTIALLY_PAID','PAID')",
            name=op.f("ck_purchases_payment_status_valid"),
        ),
        sa.CheckConstraint(
            "shipping_total >= 0 AND shipping_total < 'Infinity'::numeric",
            name=op.f("ck_purchases_shipping_total_valid"),
        ),
        sa.CheckConstraint(
            "subtotal >= 0 AND subtotal < 'Infinity'::numeric",
            name=op.f("ck_purchases_subtotal_valid"),
        ),
        sa.CheckConstraint(
            "tax_total >= 0 AND tax_total < 'Infinity'::numeric",
            name=op.f("ck_purchases_tax_total_valid"),
        ),
        sa.CheckConstraint(
            "length(trim(merchant_name_raw)) > 0 AND length(trim(purchase_type)) > 0",
            name=op.f("ck_purchases_purchase_text_nonempty"),
        ),
        sa.CheckConstraint(
            "subtotal IS NULL OR discount_total IS NULL OR tax_total IS NULL "
            "OR shipping_total IS NULL "
            "OR subtotal - discount_total + tax_total + shipping_total = grand_total",
            name=op.f("ck_purchases_totals_reconcile"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_purchases_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["merchant_id"],
            ["merchants.id"],
            name=op.f("fk_purchases_merchant_id_merchants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["receipt_id", "user_id"],
            ["receipts.id", "receipts.user_id"],
            name="fk_purchases_receipt_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_purchases_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchases")),
        sa.UniqueConstraint("id", "user_id", name="uq_purchases_id_user"),
        sa.UniqueConstraint("receipt_id", name="uq_purchases_receipt"),
    )
    op.create_index("ix_purchases_category", "purchases", ["category_id"], unique=False)
    op.create_index("ix_purchases_merchant", "purchases", ["merchant_id"], unique=False)
    op.create_index(
        "ix_purchases_user_purchased", "purchases", ["user_id", "purchased_at", "id"], unique=False
    )
    op.create_table(
        "line_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("purchase_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("raw_name", sa.String(length=500), nullable=False),
        sa.Column("normalized_name", sa.String(length=500), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column("unit_price", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("line_total", sa.Numeric(precision=20, scale=6), nullable=True),
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
        sa.CheckConstraint(
            "line_total >= 0 AND line_total < 'Infinity'::numeric",
            name=op.f("ck_line_items_line_total_valid"),
        ),
        sa.CheckConstraint(
            "quantity > 0 AND quantity < 'Infinity'::numeric",
            name=op.f("ck_line_items_quantity_valid"),
        ),
        sa.CheckConstraint(
            "unit_price >= 0 AND unit_price < 'Infinity'::numeric",
            name=op.f("ck_line_items_unit_price_valid"),
        ),
        sa.CheckConstraint(
            "length(trim(raw_name)) > 0", name=op.f("ck_line_items_raw_name_nonempty")
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_line_items_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_line_items_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_id"],
            ["purchases.id"],
            name=op.f("fk_line_items_purchase_id_purchases"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_line_items")),
    )
    op.create_index("ix_line_items_category", "line_items", ["category_id"], unique=False)
    op.create_index("ix_line_items_product", "line_items", ["product_id"], unique=False)
    op.create_index("ix_line_items_purchase", "line_items", ["purchase_id"], unique=False)
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "event_type = 'PURCHASE_CREATED'", name=op.f("ck_outbox_events_event_type_supported")
        ),
        sa.ForeignKeyConstraint(
            ["purchase_id", "user_id"],
            ["purchases.id", "purchases.user_id"],
            name="fk_outbox_events_purchase_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_events")),
        sa.UniqueConstraint("purchase_id", "event_type", name="uq_outbox_events_purchase_type"),
    )
    op.create_index(
        "ix_outbox_events_pending",
        "outbox_events",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_index("ix_outbox_events_user", "outbox_events", ["user_id"], unique=False)
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("purchase_id", sa.Uuid(), nullable=False),
        sa.Column("method", sa.String(length=40), nullable=False),
        sa.Column("amount", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=True),
        sa.Column("reference", sa.String(length=200), nullable=True),
        sa.Column("last4", sa.String(length=4), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "amount > 0 AND amount < 'Infinity'::numeric", name=op.f("ck_payments_amount_valid")
        ),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_payments_currency_valid")),
        sa.CheckConstraint(
            "last4 IS NULL OR last4 ~ '^[0-9]{4}$'", name=op.f("ck_payments_last4_valid")
        ),
        sa.CheckConstraint("length(trim(method)) > 0", name=op.f("ck_payments_method_nonempty")),
        sa.ForeignKeyConstraint(
            ["purchase_id"],
            ["purchases.id"],
            name=op.f("fk_payments_purchase_id_purchases"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
    )
    op.create_index("ix_payments_purchase", "payments", ["purchase_id"], unique=False)


def downgrade() -> None:
    # Reverse dependency order preserves the existing Milestone 1 schema.
    op.drop_index("ix_payments_purchase", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_outbox_events_user", table_name="outbox_events")
    op.drop_index(
        "ix_outbox_events_pending",
        table_name="outbox_events",
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.drop_table("outbox_events")
    op.drop_index("ix_line_items_purchase", table_name="line_items")
    op.drop_index("ix_line_items_product", table_name="line_items")
    op.drop_index("ix_line_items_category", table_name="line_items")
    op.drop_table("line_items")
    op.drop_index("ix_purchases_user_purchased", table_name="purchases")
    op.drop_index("ix_purchases_merchant", table_name="purchases")
    op.drop_index("ix_purchases_category", table_name="purchases")
    op.drop_table("purchases")
    op.drop_index("ix_extraction_runs_receipt_created", table_name="extraction_runs")
    op.drop_table("extraction_runs")
    op.drop_index("ix_receipts_user_created", table_name="receipts")
    op.drop_table("receipts")
    op.drop_index("ix_products_category", table_name="products")
    op.drop_index("ix_products_canonical_name", table_name="products")
    op.drop_table("products")
    op.drop_index("ix_merchants_normalized_name", table_name="merchants")
    op.drop_table("merchants")
    op.drop_index("ix_categories_parent", table_name="categories")
    op.drop_table("categories")
