import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import Date, String, cast, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.identity.context import CurrentUser
from backend.app.identity.models import User
from backend.app.insights.evaluation import InsightEvaluation
from backend.app.insights.service import InsightService
from backend.app.inventory.models import InventoryEvent, InventoryLot
from backend.app.purchases.errors import Conflict, DomainError, NotFound
from backend.app.purchases.models import OutboxEvent
from backend.app.purchases.queries import utc_now

logger = logging.getLogger(__name__)
INPUT_EVENTS = ("PURCHASE_CREATED", "INVENTORY_CHANGED", "INSIGHT_EVALUATION_REQUESTED")


@dataclass(frozen=True)
class InsightTask:
    event_id: UUID


class InsightWorkerRepository:
    """Privileged worker boundary: owners and lot references come from durable rows."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def ready(self, now: datetime) -> list[InsightTask]:
        return [
            InsightTask(event_id)
            for event_id in self.session.scalars(
                select(OutboxEvent.id)
                .where(
                    OutboxEvent.event_type.in_(INPUT_EVENTS),
                    OutboxEvent.insight_processed_at.is_(None),
                    OutboxEvent.insight_failed_at.is_(None),
                    OutboxEvent.insight_available_at <= now,
                )
                .order_by(OutboxEvent.insight_available_at, OutboxEvent.id)
                .limit(20)
            )
        ]

    def locked(self, task: InsightTask) -> OutboxEvent:
        event = self.session.scalar(
            select(OutboxEvent)
            .where(OutboxEvent.id == task.event_id, OutboxEvent.event_type.in_(INPUT_EVENTS))
            .with_for_update()
        )
        if event is None:
            raise NotFound
        return event

    def owner(self, event: OutboxEvent) -> tuple[CurrentUser, str]:
        row = self.session.scalars(
            select(User).where(User.id == event.user_id).with_for_update()
        ).one()
        return CurrentUser(row.id, row.firebase_uid), row.timezone

    def lot(self, event: OutboxEvent) -> UUID | None:
        if event.event_type == "INVENTORY_CHANGED":
            return self.session.scalars(
                select(InventoryEvent.lot_id).where(
                    InventoryEvent.id == event.inventory_event_id,
                    InventoryEvent.user_id == event.user_id,
                )
            ).one()
        return event.evaluation_lot_id

    def schedule(self, now: datetime) -> int:
        local_day = cast(func.timezone(User.timezone, now), Date)
        key = func.concat("financial:", local_day, ":", User.timezone)
        already = (
            select(OutboxEvent.id)
            .where(OutboxEvent.user_id == User.id, OutboxEvent.schedule_key == key)
            .exists()
        )
        owners = self.session.scalars(
            select(User)
            .where(~already)
            .order_by(User.id)
            .limit(20)
            .with_for_update(skip_locked=True)
        ).all()
        for owner in owners:
            day_key = f"{now.astimezone(ZoneInfo(owner.timezone)).date()}:{owner.timezone}"
            self.session.execute(
                insert(OutboxEvent)
                .values(
                    id=uuid4(),
                    user_id=owner.id,
                    event_type="INSIGHT_EVALUATION_REQUESTED",
                    schedule_key=f"financial:{day_key}",
                    payload={},
                    created_at=now,
                    available_at=now,
                    insight_available_at=now,
                )
                .on_conflict_do_nothing(constraint="uq_outbox_events_user_schedule")
            )
            # Set-based fan-out avoids loading the entire owner's inventory into Python.
            self.session.execute(
                insert(OutboxEvent)
                .from_select(
                    [
                        "id",
                        "user_id",
                        "evaluation_lot_id",
                        "event_type",
                        "schedule_key",
                        "payload",
                        "created_at",
                        "available_at",
                        "insight_available_at",
                    ],
                    select(
                        func.gen_random_uuid(),
                        InventoryLot.user_id,
                        InventoryLot.id,
                        literal("INSIGHT_EVALUATION_REQUESTED"),
                        func.concat("lot:", cast(InventoryLot.id, String), ":", day_key),
                        cast(literal("{}"), JSONB),
                        literal(now),
                        literal(now),
                        literal(now),
                    ).where(InventoryLot.user_id == owner.id),
                )
                .on_conflict_do_nothing(constraint="uq_outbox_events_user_schedule")
            )
        return len(owners)


class InsightProcessor:
    def __init__(
        self, factory: sessionmaker[Session], *, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self.factory, self.clock = factory, clock

    @staticmethod
    def _pending(event: OutboxEvent, now: datetime) -> bool:
        return (
            event.insight_processed_at is None
            and event.insight_failed_at is None
            and event.insight_available_at <= now
        )

    def process(self, task: InsightTask) -> None:
        try:
            with self.factory.begin() as session:
                repository = InsightWorkerRepository(session)
                event = repository.locked(task)
                now = self.clock()
                if not self._pending(event, now):
                    return
                user, zone = repository.owner(event)
                lot_id = repository.lot(event)
                evaluation = InsightEvaluation(self.factory, user, now, zone)
                candidates = (
                    evaluation.financial() if lot_id is None else evaluation.inventory(lot_id)
                )
                InsightService(session, user).record(
                    "financial" if lot_id is None else f"lot:{lot_id}", candidates, now
                )
                event.insight_attempt_count += 1
                event.insight_failure_code = None
                event.insight_processed_at = now
        except NotFound:
            raise
        except (SQLAlchemyError, DomainError, ValueError) as exc:
            logger.warning("Insight delivery failed (%s): %s", type(exc).__name__, task.event_id)
            with self.factory.begin() as session:
                event = InsightWorkerRepository(session).locked(task)
                now = self.clock()
                if not self._pending(event, now):
                    return
                event.insight_attempt_count += 1
                permanent = isinstance(exc, (DomainError, ValueError))
                event.insight_failure_code = (
                    "insight_validation_failed" if permanent else "insight_persistence_failed"
                )
                if permanent or event.insight_attempt_count >= 3:
                    event.insight_failed_at = now
                else:
                    event.insight_available_at = now + timedelta(
                        seconds=5 * 2 ** (event.insight_attempt_count - 1)
                    )

    def retry(self, event_id: UUID) -> None:
        with self.factory.begin() as session:
            event = InsightWorkerRepository(session).locked(InsightTask(event_id))
            if event.insight_processed_at is not None or event.insight_failed_at is None:
                raise Conflict
            event.insight_attempt_count = 0
            event.insight_failed_at = event.insight_failure_code = None
            event.insight_available_at = self.clock()


class InsightTaskQueue(Protocol):
    def enqueue(self, task: InsightTask) -> None: ...


class LocalInsightTaskQueue:
    def __init__(self, processor: InsightProcessor) -> None:
        self.processor = processor

    def enqueue(self, task: InsightTask) -> None:
        self.processor.process(task)


class InsightDispatcher:
    def __init__(
        self,
        factory: sessionmaker[Session],
        queue: InsightTaskQueue,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.factory, self.queue, self.clock = factory, queue, clock

    def schedule_once(self) -> int:
        with self.factory.begin() as session:
            return InsightWorkerRepository(session).schedule(self.clock())

    def dispatch_once(self) -> int:
        with self.factory.begin() as session:
            tasks = InsightWorkerRepository(session).ready(self.clock())
        for task in tasks:
            self.queue.enqueue(task)
        return len(tasks)
