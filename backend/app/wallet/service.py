from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.identity.context import CurrentUser
from backend.app.purchases.errors import Conflict, DomainError
from backend.app.purchases.queries import utc_now
from backend.app.purchases.repositories import PurchaseRepository
from backend.app.wallet.provider import WalletFailure, WalletProvider
from backend.app.wallet.repository import WalletRepository, ensure_pass, requeue
from backend.app.wallet.schemas import WalletCreate, WalletLink, WalletQuery, WalletView


class WalletIssuanceError(DomainError):
    message = "Wallet link could not be issued."

    def __init__(self, failure: WalletFailure) -> None:
        self.code = failure.code
        self.status_code = (
            504
            if failure.code == "wallet_timeout"
            else 502
            if failure.code in {"wallet_invalid_response", "wallet_rejected"}
            else 503
        )


class WalletService:
    def __init__(
        self,
        session: Session,
        user: CurrentUser,
        provider: WalletProvider,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.session, self.user, self.provider, self.clock = session, user, provider, clock
        self.repository = WalletRepository(session, user)

    def create(self, data: WalletCreate) -> WalletView:
        with self.session.begin():
            purchase = PurchaseRepository(self.session, self.user).get(data.purchase_id)
            return WalletView.model_validate(
                ensure_pass(self.session, self.user.id, purchase.id, self.clock())
            )

    def get(self, pass_id: UUID) -> WalletView:
        with self.session.begin():
            return WalletView.model_validate(self.repository.get(pass_id))

    def list(self, query: WalletQuery) -> list[WalletView]:
        with self.session.begin():
            return [WalletView.model_validate(row) for row in self.repository.list(query)]

    def sync(self, pass_id: UUID) -> WalletView:
        with self.session.begin():
            row = self.repository.get(pass_id, lock=True)
            requeue(row, self.clock())
            return WalletView.model_validate(row)

    def add_to_wallet(self, pass_id: UUID) -> WalletLink:
        with self.session.begin():
            row = self.repository.get(pass_id)
            if row.status != "SYNCED":
                raise Conflict
            assert row.class_id is not None and row.object_id is not None
            class_id, object_id = row.class_id, row.object_id
        try:
            return WalletLink(save_url=self.provider.save_link(class_id, object_id, self.clock()))
        except WalletFailure as exc:
            raise WalletIssuanceError(exc) from exc
