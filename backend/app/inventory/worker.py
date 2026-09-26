import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.identity.context import CurrentUser
from backend.app.identity.models import User
from backend.app.inventory.service import InventoryService, utc_now
from backend.app.purchases.errors import Conflict, DomainError, NotFound
from backend.app.purchases.models import OutboxEvent, Purchase

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class PurchaseTask:
    event_id: UUID


class InventoryWorkerRepository:
    """Narrow privileged boundary: identity comes from the owned durable purchase event."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def ready(self, now: datetime) -> list[PurchaseTask]:
        return [
            PurchaseTask(event_id)
            for event_id in self.session.scalars(
                select(OutboxEvent.id)
                .where(
                    OutboxEvent.event_type == "PURCHASE_CREATED",
                    OutboxEvent.published_at.is_(None),
                    OutboxEvent.failed_at.is_(None),
                    OutboxEvent.available_at <= now,
                )
                .order_by(OutboxEvent.available_at, OutboxEvent.id)
                .limit(20)
            )
        ]

    def locked(self, task: PurchaseTask) -> OutboxEvent:
        event = self.session.scalar(
            select(OutboxEvent)
            .where(
                OutboxEvent.id == task.event_id,
                OutboxEvent.event_type == "PURCHASE_CREATED",
            )
            .with_for_update()
        )
        if event is None:
            raise NotFound
        return event

    def owner(self, event: OutboxEvent) -> CurrentUser:
        user = self.session.scalars(
            select(User)
            .join(Purchase, Purchase.user_id == User.id)
            .where(
                Purchase.id == event.purchase_id,
                User.id == event.user_id,
            )
        ).one()
        return CurrentUser(user.id, user.firebase_uid)

    def failure(self, task: PurchaseTask, now: datetime, *, permanent: bool) -> None:
        event = self.locked(task)
        # Another delivery might have succeeded, failed, or rescheduled during rollback.
        if (
            event.published_at is not None
            or event.failed_at is not None
            or event.available_at > now
        ):
            return
        event.attempt_count += 1
        event.failure_code = (
            "inventory_validation_failed" if permanent else "inventory_persistence_failed"
        )
        if permanent or event.attempt_count >= MAX_ATTEMPTS:
            event.failed_at = now
        else:
            event.available_at = now + timedelta(seconds=5 * 2 ** (event.attempt_count - 1))

    def retry(self, purchase_id: UUID, now: datetime) -> None:
        event = self.session.scalar(
            select(OutboxEvent)
            .where(
                OutboxEvent.purchase_id == purchase_id,
                OutboxEvent.event_type == "PURCHASE_CREATED",
            )
            .with_for_update()
        )
        if event is None:
            raise NotFound
        if event.failed_at is None or event.published_at is not None:
            raise Conflict
        event.attempt_count = 0
        event.failed_at = event.failure_code = None
        event.available_at = now


class InventoryProcessor:
    def __init__(
        self,
        factory: sessionmaker[Session],
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.factory, self.clock = factory, clock

    def process(self, task: PurchaseTask) -> None:
        try:
            with self.factory.begin() as session:
                repository = InventoryWorkerRepository(session)
                event = repository.locked(task)
                now = self.clock()
                if (
                    event.published_at is not None
                    or event.failed_at is not None
                    or event.available_at > now
                ):
                    return
                assert event.purchase_id is not None
                InventoryService(session, repository.owner(event), clock=self.clock).apply_purchase(
                    event.purchase_id
                )
                event.attempt_count += 1
                event.failure_code = None
                event.published_at = self.clock()
        except NotFound:
            raise
        except (SQLAlchemyError, DomainError) as exc:
            logger.warning("Inventory delivery failed (%s): %s", type(exc).__name__, task.event_id)
            # If recording failure also fails, propagate: the unchanged event stays durable.
            with self.factory.begin() as session:
                InventoryWorkerRepository(session).failure(
                    task,
                    self.clock(),
                    permanent=isinstance(exc, DomainError),
                )

    def retry(self, purchase_id: UUID) -> None:
        with self.factory.begin() as session:
            InventoryWorkerRepository(session).retry(purchase_id, self.clock())


class InventoryTaskQueue(Protocol):
    def enqueue(self, task: PurchaseTask) -> None: ...


class LocalInventoryTaskQueue:
    def __init__(self, processor: InventoryProcessor) -> None:
        self.processor = processor

    def enqueue(self, task: PurchaseTask) -> None:
        self.processor.process(task)


class InventoryDispatcher:
    def __init__(
        self,
        factory: sessionmaker[Session],
        queue: InventoryTaskQueue,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.factory, self.queue, self.clock = factory, queue, clock

    def dispatch_once(self) -> int:
        with self.factory.begin() as session:
            tasks = InventoryWorkerRepository(session).ready(self.clock())
        for task in tasks:
            self.queue.enqueue(task)
        return len(tasks)
