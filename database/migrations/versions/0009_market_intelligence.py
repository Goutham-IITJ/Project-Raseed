"""market_intelligence

Revision ID: 0009_market_intelligence
Revises: 0008_google_wallet
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_market_intelligence"
down_revision = "0008_google_wallet"
branch_labels = None
depends_on = None

PREVIOUS_EVENT_CHECK = (
    "((event_type = 'PURCHASE_CREATED' AND purchase_id IS NOT NULL "
    "AND receipt_id IS NULL AND inventory_event_id IS NULL) "
    "OR (event_type = 'RECEIPT_UPLOADED' AND receipt_id IS NOT NULL "
    "AND purchase_id IS NULL AND inventory_event_id IS NULL) "
    "OR (event_type = 'INVENTORY_CHANGED' AND inventory_event_id IS NOT NULL "
    "AND purchase_id IS NULL AND receipt_id IS NULL)) "
    "AND insight_id IS NULL AND evaluation_lot_id IS NULL AND schedule_key IS NULL "
    "OR (event_type = 'INSIGHT_CREATED' AND insight_id IS NOT NULL "
    "AND purchase_id IS NULL AND receipt_id IS NULL AND inventory_event_id IS NULL "
    "AND evaluation_lot_id IS NULL AND schedule_key IS NULL) "
    "OR (event_type = 'INSIGHT_EVALUATION_REQUESTED' AND schedule_key IS NOT NULL "
    "AND length(schedule_key) > 0 AND purchase_id IS NULL AND receipt_id IS NULL "
    "AND inventory_event_id IS NULL AND insight_id IS NULL)"
)

MARKET_EVENT_CHECK = (
    "(market_search_id IS NULL AND (" + PREVIOUS_EVENT_CHECK + ")) "
    "OR (event_type = 'MARKET_SEARCH_REQUESTED' AND market_search_id IS NOT NULL "
    "AND purchase_id IS NULL AND receipt_id IS NULL AND inventory_event_id IS NULL "
    "AND insight_id IS NULL AND evaluation_lot_id IS NULL AND schedule_key IS NULL)"
)


def upgrade() -> None:
    # Add only M9 requests and external evidence; existing subscriber state is unchanged.
    op.create_table(
        "market_searches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_id", sa.Uuid(), nullable=True),
        sa.Column("line_item_id", sa.Uuid(), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("target", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'PROCESSING' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) "
            "OR (status <> 'PROCESSING' AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name=op.f("ck_market_searches_lease"),
        ),
        sa.CheckConstraint(
            "(status IN ('SUCCEEDED','FAILED')) = (completed_at IS NOT NULL) "
            "AND (status NOT IN ('RETRY','FAILED') OR failure_code IS NOT NULL) "
            "AND (status <> 'SUCCEEDED' OR (failure_code IS NULL AND expires_at IS NOT NULL))",
            name=op.f("ck_market_searches_terminal"),
        ),
        sa.CheckConstraint(
            "country ~ '^[A-Z]{2}$' AND currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_market_searches_context"),
        ),
        sa.CheckConstraint(
            "fingerprint ~ '^[a-f0-9]{64}$'", name=op.f("ck_market_searches_fingerprint")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(target) = 'object' AND octet_length(target::text) <= 8192",
            name=op.f("ck_market_searches_snapshot"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','PROCESSING','RETRY','SUCCEEDED','FAILED')",
            name=op.f("ck_market_searches_status"),
        ),
        sa.CheckConstraint(
            "(line_item_id IS NOT NULL AND purchase_id IS NOT NULL) OR "
            "(line_item_id IS NULL AND purchase_id IS NULL AND product_id IS NOT NULL)",
            name=op.f("ck_market_searches_target"),
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 0 AND 3", name=op.f("ck_market_searches_attempts")
        ),
        sa.ForeignKeyConstraint(
            ["line_item_id", "purchase_id"],
            ["line_items.id", "line_items.purchase_id"],
            name="fk_market_searches_line_purchase",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_market_searches_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_id", "user_id"],
            ["purchases.id", "purchases.user_id"],
            name="fk_market_searches_purchase_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_market_searches_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_searches")),
        sa.UniqueConstraint("id", "user_id", name="uq_market_searches_id_user"),
    )
    op.create_index(
        "ix_market_searches_active",
        "market_searches",
        ["user_id", "fingerprint"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING','PROCESSING','RETRY')"),
    )
    op.create_index(
        "ix_market_searches_owner_cache",
        "market_searches",
        ["user_id", "fingerprint", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_market_searches_ready",
        "market_searches",
        ["next_attempt_at", "id"],
        unique=False,
        postgresql_where=sa.text("status IN ('PENDING','PROCESSING','RETRY')"),
    )
    op.create_table(
        "market_price_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("search_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("offer_id", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("merchant", sa.String(length=500), nullable=False),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("price", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("shipping", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("tax", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provenance", sa.String(length=20), nullable=False),
        sa.Column("match_status", sa.String(length=20), nullable=False),
        sa.Column("match_confidence", sa.Numeric(precision=7, scale=6), nullable=False),
        sa.Column("match_rule", sa.String(length=80), nullable=False),
        sa.Column("match_provenance", sa.String(length=20), nullable=False),
        sa.Column("offer", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name=op.f("ck_market_price_observations_currency")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(offer) = 'object' AND octet_length(offer::text) <= 16384",
            name=op.f("ck_market_price_observations_offer"),
        ),
        sa.CheckConstraint(
            "length(trim(provider)) > 0 AND length(trim(offer_id)) > 0 "
            "AND length(trim(source)) > 0 AND url LIKE 'https://%'",
            name=op.f("ck_market_price_observations_source"),
        ),
        sa.CheckConstraint(
            "match_status IN ('EXACT','UNCERTAIN','MISMATCH') AND match_confidence BETWEEN 0 AND 1 "
            "AND match_provenance = 'DERIVED'",
            name=op.f("ck_market_price_observations_matching"),
        ),
        sa.CheckConstraint(
            "provenance = 'EXTERNAL'", name=op.f("ck_market_price_observations_provenance")
        ),
        sa.CheckConstraint(
            "observed_at <= fetched_at AND expires_at > observed_at",
            name=op.f("ck_market_price_observations_timestamps"),
        ),
        sa.CheckConstraint(
            "price >= 0 AND shipping >= 0 AND tax >= 0",
            name=op.f("ck_market_price_observations_prices"),
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_market_price_observations_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["search_id", "user_id"],
            ["market_searches.id", "market_searches.user_id"],
            name="fk_market_observations_search_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_market_price_observations_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_price_observations")),
        sa.UniqueConstraint(
            "search_id", "provider", "offer_id", name="uq_market_observations_offer"
        ),
    )
    op.create_index(
        "ix_market_observations_owner",
        "market_price_observations",
        ["user_id", "observed_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_market_observations_product",
        "market_price_observations",
        ["product_id", "expires_at"],
        unique=False,
    )
    op.add_column("outbox_events", sa.Column("market_search_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint(
        "uq_outbox_events_market_search", "outbox_events", ["market_search_id"]
    )
    op.create_foreign_key(
        "fk_outbox_events_market_owner",
        "outbox_events",
        "market_searches",
        ["market_search_id", "user_id"],
        ["id", "user_id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        op.f("ck_outbox_events_event_type_supported"), "outbox_events", type_="check"
    )
    op.create_check_constraint("event_type_supported", "outbox_events", MARKET_EVENT_CHECK)


def downgrade() -> None:
    op.execute("DELETE FROM outbox_events WHERE event_type = 'MARKET_SEARCH_REQUESTED'")
    op.drop_constraint(
        op.f("ck_outbox_events_event_type_supported"), "outbox_events", type_="check"
    )
    op.create_check_constraint("event_type_supported", "outbox_events", PREVIOUS_EVENT_CHECK)
    op.drop_constraint("fk_outbox_events_market_owner", "outbox_events", type_="foreignkey")
    op.drop_constraint("uq_outbox_events_market_search", "outbox_events", type_="unique")
    op.drop_column("outbox_events", "market_search_id")
    op.drop_index("ix_market_observations_product", table_name="market_price_observations")
    op.drop_index("ix_market_observations_owner", table_name="market_price_observations")
    op.drop_table("market_price_observations")
    op.drop_index(
        "ix_market_searches_ready",
        table_name="market_searches",
        postgresql_where=sa.text("status IN ('PENDING','PROCESSING','RETRY')"),
    )
    op.drop_index("ix_market_searches_owner_cache", table_name="market_searches")
    op.drop_index(
        "ix_market_searches_active",
        table_name="market_searches",
        postgresql_where=sa.text("status IN ('PENDING','PROCESSING','RETRY')"),
    )
    op.drop_table("market_searches")
