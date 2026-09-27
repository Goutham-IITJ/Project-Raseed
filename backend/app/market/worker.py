import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.market.comparison import matching
from backend.app.market.models import MarketPriceObservation, MarketSearch
from backend.app.market.provider import MarketFailure, MarketProvider
from backend.app.market.repository import locked_search
from backend.app.market.schemas import MarketQuery, ProviderResult, Target
from backend.app.purchases.models import OutboxEvent
from backend.app.purchases.queries import utc_now

logger = logging.getLogger(__name__)
TTL = timedelta(minutes=15)
LEASE = timedelta(minutes=5)


@dataclass(frozen=True)
class MarketTask:
    search_id: UUID


@dataclass(frozen=True)
class MarketClaim:
    task: MarketTask
    token: UUID
    query: MarketQuery


class MarketProcessor:
    def __init__(
        self,
        factory: sessionmaker[Session],
        provider: MarketProvider,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.factory, self.provider, self.clock = factory, provider, clock

    @staticmethod
    def _ack(session: Session, row: MarketSearch, now: datetime) -> None:
        event = session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.market_search_id == row.id, OutboxEvent.user_id == row.user_id
            )
        ).one()
        event.published_at = now

    def claim(self, task: MarketTask) -> MarketClaim | None:
        with self.factory.begin() as session:
            row = locked_search(session, task.search_id)
            now = self.clock()
            if row.status in {"SUCCEEDED", "FAILED"} or row.next_attempt_at > now:
                return None
            if row.attempt_count >= 3:
                self._failure(session, row, MarketFailure("market_lease_expired"), now)
                return None
            row.status = "PROCESSING"
            row.attempt_count += 1
            row.lease_token = uuid4()
            row.next_attempt_at = row.lease_expires_at = now + LEASE
            row.updated_at = now
            target = Target.model_validate(row.target)
            return MarketClaim(
                task,
                row.lease_token,
                MarketQuery(
                    identity=target.identity,
                    country=row.country,
                    postal_code=row.postal_code,
                    currency=row.currency,
                ),
            )

    def _failure(
        self, session: Session, row: MarketSearch, failure: MarketFailure, now: datetime
    ) -> None:
        row.failure_code, row.updated_at = failure.code, now
        row.lease_token = row.lease_expires_at = None
        if failure.retryable and row.attempt_count < 3:
            row.status = "RETRY"
            row.next_attempt_at = now + timedelta(
                seconds=max(5 * 2 ** (row.attempt_count - 1), failure.retry_after)
            )
        else:
            row.status = "FAILED"
            row.completed_at = now
            row.expires_at = now + TTL
            self._ack(session, row, now)

    def finish(
        self,
        claim: MarketClaim,
        result: ProviderResult | None,
        failure: MarketFailure | None = None,
    ) -> bool:
        with self.factory.begin() as session:
            row = locked_search(session, claim.task.search_id)
            now = self.clock()
            if (
                row.status != "PROCESSING"
                or row.lease_token != claim.token
                or row.lease_expires_at is None
                or row.lease_expires_at <= now
            ):
                return False
            if failure is not None:
                self._failure(session, row, failure, now)
                return True
            assert result is not None
            expirations = [now + TTL]
            for offer in result.offers:
                expiry = min(offer.observed_at + TTL, offer.expires_at or offer.observed_at + TTL)
                expirations.append(expiry)
                match = matching(claim.query.identity, offer)
                values = offer.model_dump(
                    mode="json",
                    exclude={
                        "offer_id",
                        "source",
                        "merchant",
                        "url",
                        "location",
                        "observed_at",
                        "price",
                        "currency",
                        "shipping",
                        "tax",
                    },
                )
                session.add(
                    MarketPriceObservation(
                        user_id=row.user_id,
                        search_id=row.id,
                        product_id=row.product_id if match.status == "EXACT" else None,
                        provider=self.provider.name,
                        offer_id=offer.offer_id,
                        source=offer.source,
                        merchant=offer.merchant,
                        url=offer.url,
                        location=offer.location,
                        currency=offer.currency,
                        price=offer.price,
                        shipping=offer.shipping,
                        tax=offer.tax,
                        observed_at=offer.observed_at,
                        fetched_at=now,
                        expires_at=expiry,
                        provenance="EXTERNAL",
                        offer=values,
                        match_status=match.status,
                        match_confidence=match.confidence,
                        match_rule="market.v1:" + match.rule,
                        match_provenance=match.provenance,
                    )
                )
            row.status, row.failure_code = "SUCCEEDED", None
            row.completed_at = row.updated_at = now
            row.expires_at = min(expirations)
            row.lease_token = row.lease_expires_at = None
            self._ack(session, row, now)
            return True

    def process(self, task: MarketTask) -> None:
        claim = self.claim(task)
        if claim is None:
            return
        result, failure = None, None
        try:
            supplied = self.provider.search(claim.query)
            if not isinstance(supplied, ProviderResult):
                raise MarketFailure("market_invalid_data")
            result = ProviderResult.model_validate(supplied.model_dump())
            if any(offer.observed_at > self.clock() for offer in result.offers):
                raise MarketFailure("market_invalid_data")
        except MarketFailure as exc:
            failure = exc
        except (ValidationError, ValueError, TypeError) as exc:
            logger.warning(
                "Invalid market data search=%s type=%s", task.search_id, type(exc).__name__
            )
            failure = MarketFailure("market_invalid_data")
        accepted = self.finish(claim, result, failure)
        logger.info(
            "Market search=%s accepted=%s result=%s",
            task.search_id,
            accepted,
            failure.code if failure else "succeeded",
        )


class MarketTaskQueue(Protocol):
    def enqueue(self, task: MarketTask) -> None: ...


class LocalMarketTaskQueue:
    def __init__(self, processor: MarketProcessor) -> None:
        self.processor = processor

    def enqueue(self, task: MarketTask) -> None:
        self.processor.process(task)


class MarketDispatcher:
    def __init__(
        self,
        factory: sessionmaker[Session],
        queue: MarketTaskQueue,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.factory, self.queue, self.clock = factory, queue, clock

    def dispatch_once(self) -> int:
        with self.factory.begin() as session:
            tasks = [
                MarketTask(search_id)
                for search_id in session.scalars(
                    select(MarketSearch.id)
                    .where(
                        MarketSearch.status.in_(("PENDING", "PROCESSING", "RETRY")),
                        MarketSearch.next_attempt_at <= self.clock(),
                    )
                    .order_by(MarketSearch.next_attempt_at, MarketSearch.id)
                    .limit(20)
                )
            ]
        for task in tasks:
            self.queue.enqueue(task)
        return len(tasks)
