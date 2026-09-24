"""Create users and preferences; no legacy schema dependency."""

import sqlalchemy as sa
from alembic import op

revision = "0001_identity"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("firebase_uid", sa.String(128), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("display_name", sa.String(256), nullable=True),
        sa.Column("currency", sa.String(3), server_default="INR", nullable=False),
        sa.Column("timezone", sa.String(100), server_default="Asia/Kolkata", nullable=False),
        sa.Column("locale", sa.String(50), server_default="en-IN", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(trim(firebase_uid)) > 0", name=op.f("ck_users_firebase_uid_nonempty")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("firebase_uid", name=op.f("uq_users_firebase_uid")),
    )
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(20), nullable=False),
        sa.Column("value", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "key IN ('currency', 'timezone', 'locale')",
            name=op.f("ck_user_preferences_supported_key"),
        ),
        sa.CheckConstraint("length(value) > 0", name=op.f("ck_user_preferences_nonempty_value")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_preferences_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_preferences")),
        sa.UniqueConstraint("user_id", "key", name="uq_user_preferences_user_key"),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
    op.drop_table("users")
