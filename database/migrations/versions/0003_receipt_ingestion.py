"""Private receipt ingestion and durable extraction delivery.

Revision ID: 0003_receipt_ingestion
Revises: 0002_purchase_foundation
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_receipt_ingestion"
down_revision = "0002_purchase_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("receipts", sa.Column("lease_token", sa.Uuid(), nullable=True))
    op.add_column("receipts", sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
    op.add_column(
        "receipts", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("receipts", sa.Column("failure_code", sa.String(100)))
    op.add_column("receipts", sa.Column("failure_message", sa.String(500)))
    op.create_check_constraint("attempt_count_nonnegative", "receipts", "attempt_count >= 0")
    op.create_check_constraint(
        "lease_pair", "receipts", "(lease_token IS NULL) = (lease_expires_at IS NULL)"
    )
    op.add_column("outbox_events", sa.Column("receipt_id", sa.Uuid(), nullable=True))
    op.add_column(
        "outbox_events",
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.alter_column("outbox_events", "purchase_id", existing_type=sa.Uuid(), nullable=True)
    op.drop_constraint(
        op.f("ck_outbox_events_event_type_supported"), "outbox_events", type_="check"
    )
    op.create_check_constraint(
        "event_type_supported",
        "outbox_events",
        "(event_type = 'PURCHASE_CREATED' AND purchase_id IS NOT NULL AND receipt_id IS NULL) "
        "OR (event_type = 'RECEIPT_UPLOADED' AND receipt_id IS NOT NULL AND purchase_id IS NULL)",
    )
    op.create_foreign_key(
        "fk_outbox_events_receipt_owner",
        "outbox_events",
        "receipts",
        ["receipt_id", "user_id"],
        ["id", "user_id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_outbox_events_receipt_type", "outbox_events", ["receipt_id", "event_type"]
    )
    op.create_index(
        "ix_outbox_events_available",
        "outbox_events",
        ["available_at", "id"],
        postgresql_where=sa.text("published_at IS NULL AND event_type = 'RECEIPT_UPLOADED'"),
    )


def downgrade() -> None:
    # Only the new delivery events are discarded; M2 purchases and events survive.
    op.execute("DELETE FROM outbox_events WHERE event_type = 'RECEIPT_UPLOADED'")
    op.drop_index("ix_outbox_events_available", table_name="outbox_events")
    op.drop_constraint("uq_outbox_events_receipt_type", "outbox_events", type_="unique")
    op.drop_constraint("fk_outbox_events_receipt_owner", "outbox_events", type_="foreignkey")
    op.drop_constraint(
        op.f("ck_outbox_events_event_type_supported"), "outbox_events", type_="check"
    )
    op.create_check_constraint(
        "event_type_supported", "outbox_events", "event_type = 'PURCHASE_CREATED'"
    )
    op.alter_column("outbox_events", "purchase_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("outbox_events", "available_at")
    op.drop_column("outbox_events", "receipt_id")
    op.drop_constraint(op.f("ck_receipts_lease_pair"), "receipts", type_="check")
    op.drop_constraint(op.f("ck_receipts_attempt_count_nonnegative"), "receipts", type_="check")
    for column in (
        "failure_message",
        "failure_code",
        "attempt_count",
        "lease_expires_at",
        "lease_token",
    ):
        op.drop_column("receipts", column)
