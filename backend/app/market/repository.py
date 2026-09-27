from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.identity.models import User
from backend.app.market.identification import identify
from backend.app.market.models import MarketPriceObservation, MarketSearch
from backend.app.market.schemas import SearchCreate, Target
from backend.app.purchases.errors import NotFound
from backend.app.purchases.models import LineItem, Product, Purchase
from backend.app.purchases.repositories import OwnedRepository


class MarketRepository(OwnedRepository):
    def lock_owner(self) -> User:
        return self._session.scalars(
            select(User).where(User.id == self._current_user.id).with_for_update()
        ).one()

    def target(
        self, command: SearchCreate, currency: str
    ) -> tuple[Target, UUID | None, UUID | None]:
        if command.line_item_id is not None:
            pair = self._session.execute(
                select(LineItem, Purchase)
                .join(Purchase, Purchase.id == LineItem.purchase_id)
                .where(
                    LineItem.id == command.line_item_id, Purchase.user_id == self._current_user.id
                )
            ).one_or_none()
            if pair is None:
                raise NotFound
            line, purchase = pair
            product = self._session.get(Product, line.product_id) if line.product_id else None
            return identify(product, line, purchase, currency), purchase.id, line.product_id
        product = self._session.scalar(
            select(Product).where(
                Product.id == command.product_id,
                select(LineItem.id)
                .join(Purchase, Purchase.id == LineItem.purchase_id)
                .where(LineItem.product_id == Product.id, Purchase.user_id == self._current_user.id)
                .exists(),
            )
        )
        if product is None:
            raise NotFound
        return identify(product, None, None, currency), None, product.id

    def get(self, search_id: UUID, *, lock: bool = False) -> MarketSearch:
        query = select(MarketSearch).where(
            MarketSearch.id == search_id, MarketSearch.user_id == self._current_user.id
        )
        row = self._session.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise NotFound
        return row

    def cached(self, fingerprint: str, now: datetime) -> MarketSearch | None:
        return self._session.scalar(
            select(MarketSearch)
            .where(
                MarketSearch.user_id == self._current_user.id,
                MarketSearch.fingerprint == fingerprint,
                (MarketSearch.status.in_(("PENDING", "PROCESSING", "RETRY")))
                | (MarketSearch.expires_at > now),
            )
            .order_by(MarketSearch.created_at.desc(), MarketSearch.id.desc())
            .limit(1)
        )

    def observations(self, search_id: UUID) -> list[MarketPriceObservation]:
        return list(
            self._session.scalars(
                select(MarketPriceObservation)
                .where(
                    MarketPriceObservation.user_id == self._current_user.id,
                    MarketPriceObservation.search_id == search_id,
                )
                .order_by(MarketPriceObservation.offer_id)
            )
        )

    def observation(self, observation_id: UUID) -> MarketPriceObservation:
        row = self._session.scalar(
            select(MarketPriceObservation).where(
                MarketPriceObservation.id == observation_id,
                MarketPriceObservation.user_id == self._current_user.id,
            )
        )
        if row is None:
            raise NotFound
        return row


def locked_search(session: Session, search_id: UUID) -> MarketSearch:
    """Internal worker boundary; public access always uses MarketRepository."""
    row = session.scalar(select(MarketSearch).where(MarketSearch.id == search_id).with_for_update())
    if row is None:
        raise NotFound
    return row
