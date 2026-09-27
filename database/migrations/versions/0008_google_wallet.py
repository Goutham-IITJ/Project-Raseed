"""google_wallet

Revision ID: 0008_google_wallet
Revises: 0007_memory_insights
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_google_wallet"
down_revision = "0007_memory_insights"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing purchases are backfilled by the independent Wallet subscriber.
    op.create_table(
        "wallet_passes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("pass_type", sa.String(length=20), nullable=False),
        sa.Column("class_id", sa.String(length=200), nullable=True),
        sa.Column("object_id", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(class_id IS NULL AND object_id IS NULL) OR "
            "(class_id IS NOT NULL AND object_id IS NOT NULL "
            "AND class_id ~ '^[0-9]+[.][A-Za-z0-9_-]+$' "
            "AND object_id ~ '^[0-9]+[.][A-Za-z0-9_-]+$')",
            name=op.f("ck_wallet_passes_identifiers"),
        ),
        sa.CheckConstraint(
            "(last_error_code IS NULL) = (last_error_at IS NULL) "
            "AND (status NOT IN ('RETRY','FAILED') OR last_error_code IS NOT NULL)",
            name=op.f("ck_wallet_passes_error"),
        ),
        sa.CheckConstraint(
            "(status = 'SYNCING' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) "
            "OR (status <> 'SYNCING' AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name=op.f("ck_wallet_passes_lease"),
        ),
        sa.CheckConstraint(
            "provider = 'GOOGLE' AND pass_type = 'GENERIC'",
            name=op.f("ck_wallet_passes_provider_type"),
        ),
        sa.CheckConstraint(
            "status <> 'SYNCED' OR (synced_at IS NOT NULL AND object_id IS NOT NULL "
            "AND last_error_code IS NULL)",
            name=op.f("ck_wallet_passes_success"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','SYNCING','RETRY','SYNCED','FAILED')",
            name=op.f("ck_wallet_passes_status"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= 3", name=op.f("ck_wallet_passes_attempts")
        ),
        sa.ForeignKeyConstraint(
            ["purchase_id", "user_id"],
            ["purchases.id", "purchases.user_id"],
            name="fk_wallet_passes_purchase_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_wallet_passes_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wallet_passes")),
        sa.UniqueConstraint("provider", "object_id", name="uq_wallet_passes_object"),
        sa.UniqueConstraint(
            "purchase_id", "provider", "pass_type", name="uq_wallet_passes_purchase"
        ),
    )
    op.create_index(
        "ix_wallet_passes_ready",
        "wallet_passes",
        ["next_attempt_at", "id"],
        unique=False,
        postgresql_where=sa.text("status IN ('PENDING','RETRY','SYNCING')"),
    )
    op.create_index(
        "ix_wallet_passes_user_created",
        "wallet_passes",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.add_column(
        "outbox_events", sa.Column("wallet_processed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_outbox_events_wallet_ready",
        "outbox_events",
        ["created_at", "id"],
        unique=False,
        postgresql_where=sa.text("wallet_processed_at IS NULL AND event_type = 'PURCHASE_CREATED'"),
    )


def downgrade() -> None:
    # Canonical data and other subscriber state survive; remote objects are untouched.
    op.drop_index(
        "ix_outbox_events_wallet_ready",
        table_name="outbox_events",
        postgresql_where=sa.text("wallet_processed_at IS NULL AND event_type = 'PURCHASE_CREATED'"),
    )
    op.drop_column("outbox_events", "wallet_processed_at")
    op.drop_index("ix_wallet_passes_user_created", table_name="wallet_passes")
    op.drop_index(
        "ix_wallet_passes_ready",
        table_name="wallet_passes",
        postgresql_where=sa.text("status IN ('PENDING','RETRY','SYNCING')"),
    )
    op.drop_table("wallet_passes")
