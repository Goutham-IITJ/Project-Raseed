import hashlib
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import Settings
from backend.app.identity.context import CurrentUser
from backend.app.ingestion.errors import (
    LeaseLost,
    ProcessingError,
    ReviewRequired,
    StorageUnavailable,
)
from backend.app.ingestion.extractor import ReceiptExtractor
from backend.app.ingestion.lifecycle import transition
from backend.app.ingestion.normalization import NormalizationRepository
from backend.app.ingestion.repository import Claim, ReceiptTask, UploadRepository, WorkerRepository
from backend.app.ingestion.schema import PROMPT_VERSION, SCHEMA_VERSION, ReceiptExtractionV1
from backend.app.ingestion.storage import ObjectStorage
from backend.app.ingestion.upload import Upload, validate_upload
from backend.app.ingestion.validation import validate_extraction
from backend.app.purchases.errors import Conflict, DomainError
from backend.app.purchases.repositories import OutboxRepository, PurchaseRepository
from backend.app.purchases.schemas import ReceiptView

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UploadService:
    def __init__(
        self,
        session: Session,
        current_user: CurrentUser,
        storage: ObjectStorage,
        settings: Settings,
    ) -> None:
        self._session = session
        self._repository = UploadRepository(session, current_user)
        self._storage = storage
        self._settings = settings

    def upload(self, upload: Upload) -> ReceiptView:
        metadata = validate_upload(upload, self._settings)
        with self._session.begin():
            reservation = self._repository.reserve(
                metadata, utc_now(), self._settings.receipt_lease_seconds
            )
        try:
            reference = self._storage.put_object(upload.data, upload.mime_type)
        except StorageUnavailable:
            with self._session.begin():
                self._repository.failed(reservation)
            raise
        try:
            with self._session.begin():
                receipt = self._repository.uploaded(reservation, reference, utc_now())
                return ReceiptView.model_validate(receipt)
        except LeaseLost as exc:
            raise Conflict from exc
        # On uncertain DB commit, retain the unique artifact rather than deleting
        # something a committed receipt may reference. Expired reservations retry.


class ReceiptProcessor:
    def __init__(
        self,
        factory: sessionmaker[Session],
        storage: ObjectStorage,
        extractor: ReceiptExtractor,
        settings: Settings,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.factory, self.storage, self.extractor = factory, storage, extractor
        self.settings, self.clock = settings, clock

    def process(self, task: ReceiptTask) -> None:
        with self.factory.begin() as session:
            claim = WorkerRepository(session).claim(
                task,
                self.clock(),
                lease_seconds=self.settings.receipt_lease_seconds,
                max_attempts=self.settings.receipt_max_attempts,
                provider=self.extractor.provider,
                model=self.extractor.model,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
            )
        if claim is None:
            return
        try:
            self._process(claim)
        except LeaseLost:
            logger.info("Receipt processing lease superseded: %s", claim.receipt_id)
        except ReviewRequired as exc:
            self._fail(claim, exc, review=True)
        except ProcessingError as exc:
            self._fail(claim, exc)
        except StorageUnavailable:
            self._fail(
                claim,
                ProcessingError(
                    "storage_unavailable",
                    "Receipt storage is unavailable.",
                    retryable=True,
                ),
            )
        except SQLAlchemyError:
            self._fail(
                claim,
                ProcessingError(
                    "persistence_failed",
                    "Canonical persistence failed.",
                    retryable=True,
                ),
            )
        except (ValidationError, DomainError):
            self._fail(
                claim,
                ReviewRequired(
                    "normalization_invalid",
                    "Normalized purchase requires review.",
                ),
                review=True,
            )
        except Exception:
            # Persist a safe failure, never provider payloads/credentials in logs.
            logger.error("Unexpected receipt processing failure: %s", claim.receipt_id)
            self._fail(
                claim,
                ProcessingError(
                    "processing_failed",
                    "Receipt processing failed; an operator may retry.",
                ),
            )

    def _process(self, claim: Claim) -> None:
        binary = self.storage.get_object(claim.storage_uri)
        if (
            len(binary) != claim.file_size
            or hashlib.sha256(binary).hexdigest() != claim.content_hash
        ):
            raise ProcessingError(
                "artifact_mismatch", "Stored receipt does not match uploaded metadata."
            )
        result = self.extractor.extract(binary, claim.mime_type, SCHEMA_VERSION)
        if len(result.text.encode("utf-8")) > 1024 * 1024:
            raise ProcessingError(
                "extraction_too_large", "Extraction response exceeds the size limit."
            )
        with self.factory.begin() as session:
            _, receipt, run = WorkerRepository(session).owned(claim, self.clock())
            transition(receipt, "EXTRACTED")
            run.raw_output = {"text": result.text}
        try:
            extraction = ReceiptExtractionV1.model_validate_json(result.text)
        except ValidationError as exc:
            raise ReviewRequired(
                "extraction_schema_invalid", "Extracted fields require review."
            ) from exc
        with self.factory.begin() as session:
            _, receipt, run = WorkerRepository(session).owned(claim, self.clock())
            transition(receipt, "VALIDATING")
            run.normalized_output = {"extraction": extraction.model_dump(mode="json")}
        command = validate_extraction(extraction, claim.receipt_id, claim.user_timezone)
        with self.factory.begin() as session:
            event, receipt, run = WorkerRepository(session).owned(claim, self.clock())
            command = NormalizationRepository(session, claim.current_user).normalize(
                command, extraction
            )
            transition(receipt, "NORMALIZED")
            session.flush()
            purchase = PurchaseRepository(session, claim.current_user).create(command)
            OutboxRepository(session, claim.current_user).record_purchase_created(purchase.id)
            run.normalized_output = {
                "extraction": extraction.model_dump(mode="json"),
                "canonical": command.model_dump(mode="json"),
                "provenance": {
                    "financial": "OBSERVED",
                    "normalized_names": "DERIVED",
                    "category_associations": "INFERRED",
                    "timestamp": "DERIVED",
                    "timezone": extraction.purchase_timezone or claim.user_timezone,
                    "timezone_source": "RECEIPT"
                    if extraction.purchase_timezone
                    or (extraction.purchase_time and extraction.purchase_time.tzinfo)
                    else "USER_PREFERENCE",
                },
            }
            now = self.clock()
            transition(receipt, "PROCESSED")
            receipt.processed_at = now
            receipt.lease_token = receipt.lease_expires_at = None
            run.status, run.completed_at = "SUCCEEDED", now
            event.published_at = now

    def _fail(self, claim: Claim, error: ProcessingError, *, review: bool = False) -> None:
        try:
            with self.factory.begin() as session:
                WorkerRepository(session).fail(
                    claim,
                    self.clock(),
                    error,
                    review=review,
                    max_attempts=self.settings.receipt_max_attempts,
                    retry_seconds=self.settings.receipt_retry_seconds,
                )
        except LeaseLost:
            logger.info("Failure belongs to an expired receipt attempt: %s", claim.receipt_id)
        except SQLAlchemyError:
            # The unacknowledged durable event and lease expiration recover this attempt.
            logger.error(
                "Could not persist receipt failure; lease recovery required: %s", claim.receipt_id
            )

    def retry(self, receipt_id: UUID) -> None:
        with self.factory.begin() as session:
            WorkerRepository(session).retry(receipt_id, self.clock())


class TaskQueue(Protocol):
    def enqueue(self, task: ReceiptTask) -> None: ...


class LocalTaskQueue:
    """Runs only in the separate dispatcher process; the outbox is the durable queue."""

    def __init__(self, processor: ReceiptProcessor) -> None:
        self.processor = processor

    def enqueue(self, task: ReceiptTask) -> None:
        self.processor.process(task)


class OutboxDispatcher:
    def __init__(
        self,
        factory: sessionmaker[Session],
        queue: TaskQueue,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.factory, self.queue, self.clock = factory, queue, clock

    def dispatch_once(self) -> int:
        with self.factory.begin() as session:
            tasks = WorkerRepository(session).ready(self.clock())
        for task in tasks:
            self.queue.enqueue(task)
        return len(tasks)
