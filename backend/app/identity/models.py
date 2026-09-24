from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(trim(firebase_uid)) > 0", name="firebase_uid_nonempty"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    firebase_uid: Mapped[str] = mapped_column(String(128), unique=True)
    email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(256))
    currency: Mapped[str] = mapped_column(String(3), server_default="INR")
    timezone: Mapped[str] = mapped_column(String(100), server_default="Asia/Kolkata")
    locale: Mapped[str] = mapped_column(String(50), server_default="en-IN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserPreference(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_user_preferences_user_key"),
        CheckConstraint("key IN ('currency', 'timezone', 'locale')", name="supported_key"),
        CheckConstraint("length(value) > 0", name="nonempty_value"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(20))
    value: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
