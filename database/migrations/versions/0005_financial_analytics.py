"""Indexes for owned financial analytics and filtered purchase history."""

from alembic import op

revision = "0005_financial_analytics"
down_revision = "0004_inventory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_purchases_user_currency_purchased",
        "purchases",
        ["user_id", "currency", "purchased_at", "id"],
    )
    op.create_index(
        "ix_purchases_user_merchant_purchased",
        "purchases",
        ["user_id", "merchant_id", "purchased_at", "id"],
    )
    op.create_index(
        "ix_purchases_user_category_purchased",
        "purchases",
        ["user_id", "category_id", "purchased_at", "id"],
    )
    op.create_index("ix_line_items_product_purchase", "line_items", ["product_id", "purchase_id"])
    op.create_index("ix_line_items_category_purchase", "line_items", ["category_id", "purchase_id"])
    op.drop_index("ix_line_items_product", table_name="line_items")
    op.drop_index("ix_line_items_category", table_name="line_items")


def downgrade() -> None:
    op.create_index("ix_line_items_product", "line_items", ["product_id"])
    op.create_index("ix_line_items_category", "line_items", ["category_id"])
    op.drop_index("ix_line_items_product_purchase", table_name="line_items")
    op.drop_index("ix_line_items_category_purchase", table_name="line_items")
    op.drop_index("ix_purchases_user_category_purchased", table_name="purchases")
    op.drop_index("ix_purchases_user_merchant_purchased", table_name="purchases")
    op.drop_index("ix_purchases_user_currency_purchased", table_name="purchases")
