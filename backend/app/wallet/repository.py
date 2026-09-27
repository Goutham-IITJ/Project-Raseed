from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.app.purchases.errors import NotFound
from backend.app.purchases.repositories import OwnedRepository
from backend.app.wallet.models import WalletPass
from backend.app.wallet.schemas import WalletQuery


def ensure_pass(session: Session, user_id: UUID, purchase_id: UUID, now: datetime) -> WalletPass:
    """Internal insert shared with the worker; caller has verified the owned purchase."""
    session.execute(
        insert(WalletPass)
        .values(
            id=uuid4(),
            user_id=user_id,
            purchase_id=purchase_id,
            provider="GOOGLE",
            pass_type="GENERIC",
            status="PENDING",
            attempt_count=0,
            next_attempt_at=now,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(constraint="uq_wallet_passes_purchase")
    )
    return session.scalars(
        select(WalletPass).where(
            WalletPass.purchase_id == purchase_id, WalletPass.user_id == user_id
        )
    ).one()


def requeue(row: WalletPass, now: datetime) -> None:
    if row.status in {"SYNCED", "FAILED"}:
        row.status = "PENDING"
        row.attempt_count = 0
        row.next_attempt_at = row.updated_at = now
        row.last_error_code = row.last_error_at = None


class WalletRepository(OwnedRepository):
    def get(self, pass_id: UUID, *, lock: bool = False) -> WalletPass:
        query = select(WalletPass).where(
            WalletPass.id == pass_id, WalletPass.user_id == self._current_user.id
        )
        row = self._session.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise NotFound
        return row

    def list(self, query: WalletQuery) -> list[WalletPass]:
        statement = select(WalletPass).where(WalletPass.user_id == self._current_user.id)
        if query.purchase_id is not None:
            statement = statement.where(WalletPass.purchase_id == query.purchase_id)
        if query.status is not None:
            statement = statement.where(WalletPass.status == query.status)
        return list(
            self._session.scalars(
                statement.order_by(WalletPass.created_at.desc(), WalletPass.id.desc())
                .limit(query.limit)
                .offset(query.offset)
            )
        )
