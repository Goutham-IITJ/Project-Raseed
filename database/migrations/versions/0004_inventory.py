"""inventory

Revision ID: 0004_inventory
Revises: 0003_receipt_ingestion
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_inventory"
down_revision = "0003_receipt_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_line_items_id_purchase", "line_items", ["id", "purchase_id"])
    op.create_table(
        "inventory_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("identity_key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(name)) > 0 AND length(trim(unit)) > 0",
            name=op.f("ck_inventory_items_text_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_inventory_items_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_inventory_items_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_items")),
        sa.UniqueConstraint("id", "user_id", name="uq_inventory_items_id_user"),
        sa.UniqueConstraint("user_id", "identity_key", name="uq_inventory_items_identity"),
    )
    op.create_index("ix_inventory_items_product", "inventory_items", ["product_id"], unique=False)
    op.create_index(
        "ix_inventory_items_user_created",
        "inventory_items",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "inventory_lots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_id", sa.Uuid(), nullable=False),
        sa.Column("line_item_id", sa.Uuid(), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["item_id", "user_id"],
            ["inventory_items.id", "inventory_items.user_id"],
            name="fk_inventory_lots_item_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["line_item_id", "purchase_id"],
            ["line_items.id", "line_items.purchase_id"],
            name="fk_inventory_lots_line_purchase",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_id", "user_id"],
            ["purchases.id", "purchases.user_id"],
            name="fk_inventory_lots_purchase_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_lots")),
        sa.UniqueConstraint("id", "user_id", name="uq_inventory_lots_id_user"),
        sa.UniqueConstraint("line_item_id", name="uq_inventory_lots_line"),
    )
    op.create_index("ix_inventory_lots_item", "inventory_lots", ["item_id"], unique=False)
    op.create_index("ix_inventory_lots_purchase", "inventory_lots", ["purchase_id"], unique=False)
    op.create_index(
        "ix_inventory_lots_user_created",
        "inventory_lots",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "inventory_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("lot_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("quantity_delta", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("actor", sa.String(length=30), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("expiry_changed", sa.Boolean(), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("expiry_source", sa.String(length=30), nullable=True),
        sa.Column("expiry_confidence", sa.Numeric(precision=7, scale=6), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(NOT expiry_changed AND expiry_date IS NULL AND expiry_source IS NULL "
            "AND expiry_confidence IS NULL) OR (expiry_changed AND "
            "event_type IN ('PURCHASED','CORRECTION') AND expiry_source IS NOT NULL AND "
            "((expiry_source = 'UNKNOWN' AND expiry_date IS NULL AND expiry_confidence IS NULL) "
            "OR (expiry_source IN ('RECEIPT','USER','PRODUCT_KNOWLEDGE','MODEL_ESTIMATE') "
            "AND expiry_date IS NOT NULL AND expiry_confidence IS NOT NULL "
            "AND expiry_confidence >= 0 AND expiry_confidence <= 1)))",
            name=op.f("ck_inventory_events_expiry_valid"),
        ),
        sa.CheckConstraint(
            "(actor = 'USER' AND source = 'USER' AND actor_user_id IS NOT NULL "
            "AND actor_user_id = user_id) OR (actor = 'INVENTORY_WORKER' "
            "AND source IN ('PURCHASE','SERVICE') AND actor_user_id IS NULL)",
            name=op.f("ck_inventory_events_actor_valid"),
        ),
        sa.CheckConstraint(
            "(event_type = 'PURCHASED' AND sequence = 1 AND quantity_delta > 0) OR "
            "(sequence > 1 AND ((event_type IN ('CONSUMED','EXPIRED','DISCARDED','RETURNED') "
            "AND quantity_delta < 0) OR (event_type = 'MANUAL_ADJUSTMENT' "
            "AND quantity_delta <> 0) OR event_type = 'CORRECTION'))",
            name=op.f("ck_inventory_events_event_valid"),
        ),
        sa.CheckConstraint(
            "quantity_delta > '-Infinity'::numeric AND quantity_delta < 'Infinity'::numeric",
            name=op.f("ck_inventory_events_delta_finite"),
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_inventory_events_request_hash_valid")
        ),
        sa.CheckConstraint(
            "length(trim(reason)) > 0", name=op.f("ck_inventory_events_reason_nonempty")
        ),
        sa.CheckConstraint("sequence > 0", name=op.f("ck_inventory_events_sequence_positive")),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_inventory_events_actor_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["lot_id", "user_id"],
            ["inventory_lots.id", "inventory_lots.user_id"],
            name="fk_inventory_events_lot_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_events")),
        sa.UniqueConstraint("id", "user_id", name="uq_inventory_events_id_user"),
        sa.UniqueConstraint("lot_id", "sequence", name="uq_inventory_events_sequence"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_inventory_events_idempotency"),
    )
    op.create_index(
        "ix_inventory_events_expiry",
        "inventory_events",
        ["lot_id", "sequence"],
        unique=False,
        postgresql_where=sa.text("expiry_changed"),
    )
    op.create_index(
        "ix_inventory_events_user_created",
        "inventory_events",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.add_column("categories", sa.Column("inventory_eligible", sa.Boolean(), nullable=True))
    op.add_column("outbox_events", sa.Column("inventory_event_id", sa.Uuid(), nullable=True))
    op.add_column(
        "outbox_events",
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("outbox_events", sa.Column("failure_code", sa.String(length=100), nullable=True))
    op.add_column(
        "outbox_events", sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_outbox_events_inventory_ready",
        "outbox_events",
        ["available_at", "id"],
        unique=False,
        postgresql_where=sa.text(
            "published_at IS NULL AND failed_at IS NULL AND event_type = 'PURCHASE_CREATED'"
        ),
    )
    op.create_unique_constraint(
        "uq_outbox_events_inventory_event", "outbox_events", ["inventory_event_id"]
    )
    op.create_foreign_key(
        "fk_outbox_events_inventory_owner",
        "outbox_events",
        "inventory_events",
        ["inventory_event_id", "user_id"],
        ["id", "user_id"],
        ondelete="RESTRICT",
    )
    op.add_column("products", sa.Column("inventory_eligible", sa.Boolean(), nullable=True))
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
    op.create_check_constraint("attempt_count_nonnegative", "outbox_events", "attempt_count >= 0")
    op.execute("""
        CREATE FUNCTION inventory_ledger_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE previous_sequence integer; balance numeric;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'Inventory history is append-only' USING ERRCODE = '23514';
            END IF;
            PERFORM id FROM users WHERE id = NEW.user_id FOR UPDATE;
            SELECT COALESCE(MAX(sequence), 0), COALESCE(SUM(quantity_delta), 0)
                INTO previous_sequence, balance FROM inventory_events WHERE lot_id = NEW.lot_id;
            IF NEW.sequence <> previous_sequence + 1 OR balance + NEW.quantity_delta < 0
                OR balance + NEW.quantity_delta > 99999999999999.999999 THEN
                RAISE EXCEPTION 'Invalid inventory sequence or balance' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER inventory_ledger_guard
        BEFORE INSERT OR UPDATE OR DELETE ON inventory_events
        FOR EACH ROW EXECUTE FUNCTION inventory_ledger_guard()
    """)


def downgrade() -> None:
    # Downgrade intentionally removes M4 history. Never run on production inventory.
    op.execute("DELETE FROM outbox_events WHERE event_type = 'INVENTORY_CHANGED'")
    op.execute(
        "UPDATE outbox_events SET published_at = NULL, available_at = now() "
        "WHERE event_type = 'PURCHASE_CREATED' AND attempt_count > 0"
    )
    op.drop_constraint(
        op.f("ck_outbox_events_event_type_supported"), "outbox_events", type_="check"
    )
    op.drop_constraint(
        op.f("ck_outbox_events_attempt_count_nonnegative"), "outbox_events", type_="check"
    )
    op.create_check_constraint(
        "event_type_supported",
        "outbox_events",
        "(event_type = 'PURCHASE_CREATED' AND purchase_id IS NOT NULL AND receipt_id IS NULL) "
        "OR (event_type = 'RECEIPT_UPLOADED' AND receipt_id IS NOT NULL AND purchase_id IS NULL)",
    )
    op.drop_column("products", "inventory_eligible")
    op.drop_constraint("fk_outbox_events_inventory_owner", "outbox_events", type_="foreignkey")
    op.drop_constraint("uq_outbox_events_inventory_event", "outbox_events", type_="unique")
    op.drop_index(
        "ix_outbox_events_inventory_ready",
        table_name="outbox_events",
        postgresql_where=sa.text(
            "published_at IS NULL AND failed_at IS NULL AND event_type = 'PURCHASE_CREATED'"
        ),
    )
    op.drop_column("outbox_events", "failed_at")
    op.drop_column("outbox_events", "failure_code")
    op.drop_column("outbox_events", "attempt_count")
    op.drop_column("outbox_events", "inventory_event_id")
    op.drop_column("categories", "inventory_eligible")
    op.drop_index("ix_inventory_events_user_created", table_name="inventory_events")
    op.drop_index(
        "ix_inventory_events_expiry",
        table_name="inventory_events",
        postgresql_where=sa.text("expiry_changed"),
    )
    op.drop_table("inventory_events")
    op.execute("DROP FUNCTION inventory_ledger_guard()")
    op.drop_index("ix_inventory_lots_user_created", table_name="inventory_lots")
    op.drop_index("ix_inventory_lots_purchase", table_name="inventory_lots")
    op.drop_index("ix_inventory_lots_item", table_name="inventory_lots")
    op.drop_table("inventory_lots")
    op.drop_constraint("uq_line_items_id_purchase", "line_items", type_="unique")
    op.drop_index("ix_inventory_items_user_created", table_name="inventory_items")
    op.drop_index("ix_inventory_items_product", table_name="inventory_items")
    op.drop_table("inventory_items")
