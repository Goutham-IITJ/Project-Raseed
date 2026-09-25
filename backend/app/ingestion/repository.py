from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.app.identity.context import CurrentUser
from backend.app.identity.models import User
from backend.app.ingestion.errors import LeaseLost, ProcessingError
from backend.app.ingestion.lifecycle import transition
from backend.app.purchases.errors import Conflict, NotFound
from backend.app.purchases.models import ExtractionRun, OutboxEvent, Receipt
from backend.app.purchases.repositories import ReceiptRepository
from backend.app.purchases.schemas import ReceiptCreate


@dataclass(frozen=True)
class Reservation:
    receipt_id: UUID
    token: UUID


class UploadRepository(ReceiptRepository):
    def reserve(self, metadata: ReceiptCreate, now: datetime, lease_seconds: int) -> Reservation:
        self._session.execute(
            insert(Receipt)
            .values(id=uuid4(), user_id=self._current_user.id, **metadata.model_dump())
            .on_conflict_do_nothing(constraint="uq_receipts_user_content_hash")
        )
        receipt = self._session.scalars(
            select(Receipt)
            .where(
                Receipt.user_id == self._current_user.id,
                Receipt.content_hash == metadata.content_hash,
            )
            .with_for_update()
        ).one()
        if receipt.storage_uri is not None or (
            receipt.lease_expires_at is not None and receipt.lease_expires_at > now
        ):
            raise Conflict
        if receipt.status == "FAILED":
            transition(receipt, "PENDING_UPLOAD")
        if receipt.status != "PENDING_UPLOAD":
            raise Conflict
        for field, value in metadata.model_dump().items():
            setattr(receipt, field, value)
        receipt.failure_code = receipt.failure_message = None
        receipt.lease_token = uuid4()
        receipt.lease_expires_at = now + timedelta(seconds=lease_seconds)
        self._session.flush()
        return Reservation(receipt.id, receipt.lease_token)

    def locked(self, reservation: Reservation) -> Receipt:
        receipt = self._session.scalar(
            select(Receipt)
            .where(
                Receipt.id == reservation.receipt_id,
                Receipt.user_id == self._current_user.id,
            )
            .with_for_update()
        )
        if receipt is None or receipt.lease_token != reservation.token:
            raise LeaseLost
        return receipt

    def uploaded(self, reservation: Reservation, reference: str, now: datetime) -> Receipt:
        receipt = self.locked(reservation)
        transition(receipt, "UPLOADED")
        receipt.storage_uri = reference
        receipt.uploaded_at = now
        receipt.lease_token = receipt.lease_expires_at = None
        self._session.add(
            OutboxEvent(
                user_id=self._current_user.id,
                receipt_id=receipt.id,
                event_type="RECEIPT_UPLOADED",
                payload={"receipt_id": str(receipt.id)},
                available_at=now,
            )
        )
        self._session.flush()
        return receipt

    def failed(self, reservation: Reservation) -> None:
        receipt = self.locked(reservation)
        transition(receipt, "FAILED")
        receipt.failure_code = "upload_storage_failed"
        receipt.failure_message = "Receipt storage failed; upload the same file again to retry."
        receipt.lease_token = receipt.lease_expires_at = None


@dataclass(frozen=True)
class ReceiptTask:
    event_id: UUID


@dataclass(frozen=True)
class Claim:
    task: ReceiptTask
    receipt_id: UUID
    run_id: UUID
    token: UUID
    current_user: CurrentUser
    user_timezone: str
    storage_uri: str
    mime_type: str
    content_hash: str
    file_size: int


class WorkerRepository:
    """Privileged but narrow: trusted outbox task IDs resolve their own database owner."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def ready(self, now: datetime, limit: int = 20) -> list[ReceiptTask]:
        return [
            ReceiptTask(event_id)
            for event_id in self.session.scalars(
                select(OutboxEvent.id)
                .join(Receipt, Receipt.id == OutboxEvent.receipt_id)
                .where(
                    OutboxEvent.event_type == "RECEIPT_UPLOADED",
                    OutboxEvent.published_at.is_(None),
                    OutboxEvent.available_at <= now,
                    or_(Receipt.lease_expires_at.is_(None), Receipt.lease_expires_at <= now),
                )
                .order_by(OutboxEvent.available_at, OutboxEvent.id)
                .limit(limit)
            )
        ]

    def _locked(self, task: ReceiptTask) -> tuple[OutboxEvent, Receipt]:
        event = self.session.scalar(
            select(OutboxEvent)
            .where(
                OutboxEvent.id == task.event_id,
                OutboxEvent.event_type == "RECEIPT_UPLOADED",
            )
            .with_for_update()
        )
        if event is None:
            raise NotFound
        receipt = self.session.scalars(
            select(Receipt)
            .where(
                Receipt.id == event.receipt_id,
                Receipt.user_id == event.user_id,
            )
            .with_for_update()
        ).one()
        return event, receipt

    def claim(
        self,
        task: ReceiptTask,
        now: datetime,
        *,
        lease_seconds: int,
        max_attempts: int,
        provider: str,
        model: str,
        prompt_version: str,
        schema_version: str,
    ) -> Claim | None:
        event, receipt = self._locked(task)
        if event.published_at is not None or event.available_at > now:
            return None
        if receipt.lease_expires_at is not None and receipt.lease_expires_at > now:
            return None
        if receipt.status in {"PROCESSED", "NEEDS_REVIEW"}:
            event.published_at = now
            return None
        for run in self.session.scalars(
            select(ExtractionRun).where(
                ExtractionRun.receipt_id == receipt.id,
                ExtractionRun.status == "RUNNING",
            )
        ):
            run.status = "FAILED"
            run.completed_at = now
            run.error_code = "worker_lease_expired"
            run.error_message = (
                "Previous processing attempt did not finish before its lease expired."
            )
        if receipt.status in {"PROCESSING", "EXTRACTED", "VALIDATING", "NORMALIZED"}:
            transition(receipt, "FAILED")
        if receipt.attempt_count >= max_attempts:
            if receipt.status != "FAILED":
                transition(receipt, "FAILED")
            receipt.failure_code = "attempts_exhausted"
            receipt.failure_message = "Processing attempts exhausted; an operator may retry."
            receipt.lease_token = receipt.lease_expires_at = None
            event.published_at = now
            return None
        transition(receipt, "PROCESSING")
        receipt.lease_token = uuid4()
        receipt.lease_expires_at = now + timedelta(seconds=lease_seconds)
        receipt.attempt_count += 1
        receipt.failure_code = receipt.failure_message = None
        run = ExtractionRun(
            receipt_id=receipt.id,
            provider=provider,
            model=model or "unconfigured",
            prompt_version=prompt_version,
            schema_version=schema_version,
            status="RUNNING",
            started_at=now,
        )
        self.session.add(run)
        self.session.flush()
        user = self.session.get(User, receipt.user_id)
        assert user is not None
        return Claim(
            task,
            receipt.id,
            run.id,
            receipt.lease_token,
            CurrentUser(user.id, user.firebase_uid),
            user.timezone,
            receipt.storage_uri or "",
            receipt.mime_type,
            receipt.content_hash,
            receipt.file_size,
        )

    def owned(self, claim: Claim, now: datetime) -> tuple[OutboxEvent, Receipt, ExtractionRun]:
        event, receipt = self._locked(claim.task)
        if (
            receipt.lease_token != claim.token
            or receipt.lease_expires_at is None
            or receipt.lease_expires_at <= now
        ):
            raise LeaseLost
        run = self.session.get(ExtractionRun, claim.run_id)
        assert run is not None and run.receipt_id == receipt.id
        return event, receipt, run

    def fail(
        self,
        claim: Claim,
        now: datetime,
        error: ProcessingError,
        *,
        review: bool,
        max_attempts: int,
        retry_seconds: int,
    ) -> None:
        event, receipt, run = self.owned(claim, now)
        transition(receipt, "NEEDS_REVIEW" if review else "FAILED")
        receipt.failure_code, receipt.failure_message = error.code, error.message
        receipt.lease_token = receipt.lease_expires_at = None
        run.status, run.completed_at = "FAILED", now
        run.error_code, run.error_message = error.code, error.message
        if error.retryable and not review and receipt.attempt_count < max_attempts:
            event.available_at = now + timedelta(
                seconds=min(
                    retry_seconds * 2 ** (receipt.attempt_count - 1),
                    3600,
                )
            )
        else:
            event.published_at = now

    def retry(self, receipt_id: UUID, now: datetime) -> None:
        event_id = self.session.scalar(
            select(OutboxEvent.id).where(
                OutboxEvent.receipt_id == receipt_id,
                OutboxEvent.event_type == "RECEIPT_UPLOADED",
            )
        )
        if event_id is None:
            raise NotFound
        event, receipt = self._locked(ReceiptTask(event_id))
        if receipt.status not in {"FAILED", "NEEDS_REVIEW"} or not receipt.storage_uri:
            raise Conflict
        transition(receipt, "UPLOADED")
        receipt.attempt_count = 0
        receipt.failure_code = receipt.failure_message = None
        receipt.lease_token = receipt.lease_expires_at = None
        event.published_at, event.available_at = None, now
