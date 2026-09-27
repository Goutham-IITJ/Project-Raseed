import hashlib
import json
from collections.abc import Callable
from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.identity.context import CurrentUser
from backend.app.market.comparison import compare
from backend.app.market.models import MarketPriceObservation, MarketSearch
from backend.app.market.repository import MarketRepository
from backend.app.market.schemas import (
    Matching,
    ObservationView,
    Offer,
    SearchCreate,
    SearchView,
    Target,
)
from backend.app.purchases.errors import Conflict
from backend.app.purchases.models import OutboxEvent
from backend.app.purchases.queries import utc_now


def observation_view(
    row: MarketPriceObservation, search: MarketSearch, now: datetime
) -> ObservationView:
    offer = Offer.model_validate(
        {
            **row.offer,
            "offer_id": row.offer_id,
            "source": row.source,
            "merchant": row.merchant,
            "url": row.url,
            "location": row.location,
            "observed_at": row.observed_at,
            "price": row.price,
            "currency": row.currency,
            "shipping": row.shipping,
            "tax": row.tax,
        }
    )
    return ObservationView(
        id=row.id,
        search_id=row.search_id,
        product_id=row.product_id,
        provider=row.provider,
        offer=offer,
        fetched_at=row.fetched_at,
        expires_at=row.expires_at,
        stale=row.expires_at <= now,
        comparison=compare(
            Target.model_validate(search.target),
            offer,
            search.country,
            row.expires_at,
            now,
            match=Matching.model_validate(
                {
                    "status": row.match_status,
                    "confidence": row.match_confidence,
                    "rule": row.match_rule,
                    "provenance": row.match_provenance,
                }
            ),
        ),
    )


class MarketService:
    def __init__(
        self, session: Session, user: CurrentUser, *, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self.session, self.user, self.clock = session, user, clock
        self.repository = MarketRepository(session, user)

    def _view(self, row: MarketSearch, now: datetime) -> SearchView:
        return SearchView(
            id=row.id,
            line_item_id=row.line_item_id,
            product_id=row.product_id,
            country=row.country,
            postal_code=row.postal_code,
            target=Target.model_validate(row.target),
            status=cast(
                Literal["PENDING", "PROCESSING", "RETRY", "SUCCEEDED", "FAILED"], row.status
            ),
            attempt_count=row.attempt_count,
            failure_code=row.failure_code,
            next_attempt_at=row.next_attempt_at,
            created_at=row.created_at,
            completed_at=row.completed_at,
            expires_at=row.expires_at,
            observations=[
                observation_view(item, row, now) for item in self.repository.observations(row.id)
            ],
        )

    def search(self, command: SearchCreate) -> SearchView:
        command = SearchCreate.model_validate(command.model_dump())
        with self.session.begin():
            now = self.clock()
            owner = self.repository.lock_owner()
            target, purchase_id, product_id = self.repository.target(command, owner.currency)
            fingerprint = hashlib.sha256(
                json.dumps(
                    {
                        "request": command.model_dump(mode="json"),
                        "target": target.model_dump(mode="json"),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            cached = self.repository.cached(fingerprint, now)
            if cached is not None:
                return self._view(cached, now)
            row = MarketSearch(
                user_id=owner.id,
                purchase_id=purchase_id,
                line_item_id=command.line_item_id,
                product_id=product_id,
                target=target.model_dump(mode="json"),
                currency=target.currency,
                country=command.country,
                postal_code=command.postal_code,
                fingerprint=fingerprint,
                status="PENDING",
                attempt_count=0,
                next_attempt_at=now,
                created_at=now,
                updated_at=now,
            )
            self.session.add(row)
            self.session.flush()
            self.session.add(
                OutboxEvent(
                    user_id=owner.id,
                    market_search_id=row.id,
                    event_type="MARKET_SEARCH_REQUESTED",
                    payload={},
                    created_at=now,
                    available_at=now,
                )
            )
            self.session.flush()
            return self._view(row, now)

    def get(self, search_id: UUID) -> SearchView:
        with self.session.begin():
            return self._view(self.repository.get(search_id), self.clock())

    def observation(self, observation_id: UUID) -> ObservationView:
        with self.session.begin():
            row = self.repository.observation(observation_id)
            return observation_view(row, self.repository.get(row.search_id), self.clock())

    def retry(self, search_id: UUID) -> SearchView:
        with self.session.begin():
            self.repository.lock_owner()
            row = self.repository.get(search_id, lock=True)
            if row.status != "FAILED":
                raise Conflict
            active = self.session.scalar(
                select(MarketSearch.id).where(
                    MarketSearch.user_id == self.user.id,
                    MarketSearch.fingerprint == row.fingerprint,
                    MarketSearch.status.in_(("PENDING", "PROCESSING", "RETRY")),
                )
            )
            if active is not None:
                raise Conflict
            row.status, row.attempt_count = "PENDING", 0
            row.failure_code = row.completed_at = row.expires_at = None
            row.next_attempt_at = row.updated_at = self.clock()
            event = self.session.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.market_search_id == row.id, OutboxEvent.user_id == self.user.id
                )
            ).one()
            event.published_at = None
            return self._view(row, self.clock())
