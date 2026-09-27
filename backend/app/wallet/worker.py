import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.purchases.errors import Conflict, NotFound
from backend.app.purchases.models import OutboxEvent, Purchase
from backend.app.purchases.queries import utc_now
from backend.app.wallet.models import WalletPass
from backend.app.wallet.provider import WalletFailure, WalletProjection, WalletProvider
from backend.app.wallet.repository import ensure_pass, requeue

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
LEASE_SECONDS = 300


@dataclass(frozen=True)
class WalletTask:
    pass_id: UUID


@dataclass(frozen=True)
class WalletClaim:
    task: WalletTask
    token: UUID
    projection: WalletProjection | None
    failure: WalletFailure | None = None


class WalletWorkerRepository:
    """Privileged worker queries derive ownership from durable, foreign-keyed rows."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def handoff(self, now: datetime) -> int:
        events = self.session.scalars(
            select(OutboxEvent)
            .where(
                OutboxEvent.event_type == "PURCHASE_CREATED",
                OutboxEvent.wallet_processed_at.is_(None),
            )
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .limit(20)
            .with_for_update(skip_locked=True)
        ).all()
        for event in events:
            assert event.purchase_id is not None
            ensure_pass(self.session, event.user_id, event.purchase_id, now)
            event.wallet_processed_at = now
        return len(events)

    def ready(self, now: datetime) -> list[WalletTask]:
        return [
            WalletTask(pass_id)
            for pass_id in self.session.scalars(
                select(WalletPass.id)
                .where(
                    WalletPass.status.in_(("PENDING", "RETRY", "SYNCING")),
                    WalletPass.next_attempt_at <= now,
                )
                .order_by(WalletPass.next_attempt_at, WalletPass.id)
                .limit(20)
            )
        ]

    def locked(self, task: WalletTask) -> WalletPass:
        row = self.session.scalar(
            select(WalletPass).where(WalletPass.id == task.pass_id).with_for_update()
        )
        if row is None:
            raise NotFound
        return row

    def projection(self, row: WalletPass) -> WalletProjection:
        purchase = self.session.scalars(
            select(Purchase).where(Purchase.id == row.purchase_id, Purchase.user_id == row.user_id)
        ).one()
        assert row.class_id is not None and row.object_id is not None
        return WalletProjection(
            row.class_id,
            row.object_id,
            purchase.merchant_name_raw,
            purchase.purchased_at,
            purchase.currency,
            purchase.grand_total,
            purchase.payment_status,
        )


class WalletProcessor:
    def __init__(
        self,
        factory: sessionmaker[Session],
        provider: WalletProvider,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.factory, self.provider, self.clock = factory, provider, clock

    def claim(self, task: WalletTask) -> WalletClaim | None:
        with self.factory.begin() as session:
            repository = WalletWorkerRepository(session)
            row = repository.locked(task)
            now = self.clock()
            if row.status in {"SYNCED", "FAILED"} or row.next_attempt_at > now:
                return None
            if row.attempt_count >= MAX_ATTEMPTS:
                self._failed(row, WalletFailure("wallet_lease_expired"), now)
                return None
            row.status = "SYNCING"
            row.attempt_count += 1
            row.lease_token = uuid4()
            row.lease_expires_at = row.next_attempt_at = now + timedelta(seconds=LEASE_SECONDS)
            row.updated_at = now
            try:
                class_id, object_id = self.provider.identifiers(row.purchase_id)
                if row.class_id is None:
                    row.class_id, row.object_id = class_id, object_id
                elif (row.class_id, row.object_id) != (class_id, object_id):
                    raise WalletFailure("wallet_configuration")
            except WalletFailure as exc:
                return WalletClaim(task, row.lease_token, None, exc)
            return WalletClaim(task, row.lease_token, repository.projection(row))

    @staticmethod
    def _failed(row: WalletPass, failure: WalletFailure, now: datetime) -> None:
        row.last_error_code, row.last_error_at = failure.code, now
        row.updated_at = now
        row.lease_token = row.lease_expires_at = None
        if failure.retryable and row.attempt_count < MAX_ATTEMPTS:
            row.status = "RETRY"
            row.next_attempt_at = now + timedelta(
                seconds=max(5 * 2 ** (row.attempt_count - 1), failure.retry_after)
            )
        else:
            row.status = "FAILED"
            row.next_attempt_at = now

    def finish(self, claim: WalletClaim, failure: WalletFailure | None = None) -> bool:
        with self.factory.begin() as session:
            row = WalletWorkerRepository(session).locked(claim.task)
            now = self.clock()
            if (
                row.status != "SYNCING"
                or row.lease_token != claim.token
                or row.lease_expires_at is None
                or row.lease_expires_at <= now
            ):
                return False
            if failure is not None:
                self._failed(row, failure, now)
            else:
                row.status = "SYNCED"
                row.synced_at = row.updated_at = now
                row.next_attempt_at = now
                row.lease_token = row.lease_expires_at = None
                row.last_error_code = row.last_error_at = None
            return True

    def process(self, task: WalletTask) -> None:
        claim = self.claim(task)
        if claim is None:
            return
        failure = claim.failure
        if failure is None:
            assert claim.projection is not None
            try:
                self.provider.sync(claim.projection)
            except WalletFailure as exc:
                failure = exc
        accepted = self.finish(claim, failure)
        logger.info(
            "Wallet sync pass=%s accepted=%s result=%s",
            task.pass_id,
            accepted,
            failure.code if failure else "synced",
        )

    def retry(self, pass_id: UUID) -> None:
        with self.factory.begin() as session:
            row = WalletWorkerRepository(session).locked(WalletTask(pass_id))
            if row.status != "FAILED":
                raise Conflict
            requeue(row, self.clock())


class WalletTaskQueue(Protocol):
    def enqueue(self, task: WalletTask) -> None: ...


class LocalWalletTaskQueue:
    def __init__(self, processor: WalletProcessor) -> None:
        self.processor = processor

    def enqueue(self, task: WalletTask) -> None:
        self.processor.process(task)


class WalletDispatcher:
    def __init__(
        self,
        factory: sessionmaker[Session],
        queue: WalletTaskQueue,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.factory, self.queue, self.clock = factory, queue, clock

    def dispatch_once(self) -> int:
        with self.factory.begin() as session:
            WalletWorkerRepository(session).handoff(self.clock())
        with self.factory.begin() as session:
            tasks = WalletWorkerRepository(session).ready(self.clock())
        for task in tasks:
            self.queue.enqueue(task)
        return len(tasks)
