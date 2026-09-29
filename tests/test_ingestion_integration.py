import json
import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from threading import Event, Thread
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
import uvicorn
from conftest import FakeVerifier
from fastapi.testclient import TestClient
from ingestion_fixtures import FakeExtractor, document, evidence
from pypdf import PdfWriter
from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError, OperationalError

from backend.app.config import Settings
from backend.app.database import make_session_factory
from backend.app.identity.context import CurrentUser
from backend.app.ingestion.errors import ProcessingError, StorageUnavailable
from backend.app.ingestion.repository import ReceiptTask, UploadRepository
from backend.app.ingestion.service import (
    LocalTaskQueue,
    OutboxDispatcher,
    ReceiptProcessor,
    UploadService,
)
from backend.app.ingestion.storage import LocalStorageProvider
from backend.app.ingestion.upload import Upload, validate_upload
from backend.app.main import create_app
from backend.app.purchases.errors import Conflict
from backend.app.purchases.models import (
    Category,
    ExtractionRun,
    LineItem,
    Merchant,
    OutboxEvent,
    Payment,
    Product,
    Purchase,
    Receipt,
)
from backend.app.purchases.repositories import OutboxRepository
from backend.app.purchases.schemas import CategoryCreate
from backend.app.purchases.service import PurchaseService

pytestmark = pytest.mark.integration
ALICE = {"Authorization": "Bearer alice-token"}
BOB = {"Authorization": "Bearer bob-token"}


@pytest.fixture
def ingestion(database, tmp_path):
    settings = Settings(firebase_project_id="test", local_storage_path=tmp_path / "private")
    storage = LocalStorageProvider(settings.local_storage_path)
    factory = make_session_factory(database)
    extractor = FakeExtractor()
    env = SimpleNamespace(
        settings=settings, storage=storage, factory=factory, extractor=extractor, offset=timedelta()
    )
    env.clock = lambda: datetime.now(timezone.utc) + env.offset
    env.processor = ReceiptProcessor(factory, storage, extractor, settings, clock=env.clock)
    env.dispatcher = OutboxDispatcher(factory, LocalTaskQueue(env.processor), clock=env.clock)
    app = create_app(settings, verifier=FakeVerifier(), session_factory=factory, storage=storage)
    with TestClient(app) as client:
        env.client = client
        yield env


def upload(env, kind="png", headers=ALICE, data=None, filename=None, mime=None):
    mime = (
        mime
        or {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "pdf": "application/pdf",
        }[kind]
    )
    return env.client.post(
        "/api/v1/receipts",
        headers=headers,
        files={
            "file": (filename or f"receipt.{kind}", document(kind) if data is None else data, mime)
        },
    )


def event_task(env, receipt_id):
    with env.factory() as session:
        event = session.scalars(
            select(OutboxEvent).where(OutboxEvent.receipt_id == UUID(receipt_id))
        ).one()
        return ReceiptTask(event.id)


def assert_no_canonical(env):
    with env.factory() as session:
        for model in (Purchase, LineItem, Payment, Merchant, Product):
            assert session.scalar(select(func.count()).select_from(model)) == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.event_type == "PURCHASE_CREATED")
            )
            == 0
        )


@pytest.mark.parametrize("kind", ["jpg", "jpeg", "png", "pdf"])
def test_upload_to_processed_with_real_local_storage_and_fake_extractor(ingestion, kind):
    env = ingestion
    response = upload(env, kind)
    assert response.status_code == 202
    receipt = response.json()["data"]
    assert receipt["status"] == "UPLOADED" and receipt["purchase_id"] is None
    assert receipt["uploaded_at"] is not None and response.headers["cache-control"] == "no-store"
    assert env.extractor.calls == []
    assert "storage_uri" not in receipt and "user_id" not in receipt
    with env.factory() as session:
        stored = session.get(Receipt, UUID(receipt["id"]))
        assert env.storage.get_object(stored.storage_uri) == document(kind)
        event = session.scalars(select(OutboxEvent)).one()
        assert event.event_type == "RECEIPT_UPLOADED" and event.published_at is None
        assert event.payload == {"receipt_id": receipt["id"]}
    assert env.dispatcher.dispatch_once() == 1
    assert env.dispatcher.dispatch_once() == 0
    result = env.client.get(f"/api/v1/receipts/{receipt['id']}", headers=ALICE).json()["data"]
    assert result["status"] == "PROCESSED" and result["purchase_id"]
    assert result["attempt_count"] == 1 and result["failure_code"] is None
    assert len(env.extractor.calls) == 1
    purchase = env.client.get(f"/api/v1/purchases/{result['purchase_id']}", headers=ALICE).json()[
        "data"
    ]
    assert Decimal(purchase["grand_total"]) == Decimal("11")
    assert purchase["line_items"][0]["normalized_name"] == "test item"
    assert Decimal(purchase["payments"][0]["amount"]) == Decimal("11")
    with env.factory() as session:
        run = session.scalars(select(ExtractionRun)).one()
        assert run.status == "SUCCEEDED" and run.schema_version == "receipt.v1"
        assert run.provider == "fixture" and run.model == "deterministic-receipt-v1"
        assert run.raw_output["text"] == env.extractor.output
        assert run.normalized_output["extraction"]["invoice_number"] == "TEST-001"
        assert run.normalized_output["provenance"]["timezone_source"] == "USER_PREFERENCE"
        events = list(session.scalars(select(OutboxEvent)))
        assert {event.event_type for event in events} == {"RECEIPT_UPLOADED", "PURCHASE_CREATED"}
        assert (
            next(event for event in events if event.event_type == "PURCHASE_CREATED").published_at
            is None
        )


@pytest.mark.parametrize(
    "filename,mime,data,status",
    [
        ("image.gif", "image/gif", b"GIF89A", 415),
        ("image.png", "image/jpeg", document(), 415),
        ("image.png", "image/png", b"not an image", 415),
        ("file.pdf", "application/pdf", b"%PDF-invalid", 415),
        ("empty.png", "image/png", b"", 415),
        ("../image.png", "image/png", document(), 422),
    ],
)
def test_upload_rejects_unsupported_invalid_and_path_filenames(
    ingestion, filename, mime, data, status
):
    response = upload(ingestion, filename=filename, mime=mime, data=data)
    assert response.status_code == status
    assert_no_canonical(ingestion)
    with ingestion.factory() as session:
        assert session.scalar(select(func.count()).select_from(Receipt)) == 0


def test_encrypted_and_excess_page_pdf_rejected(ingestion):
    pdf = PdfWriter()
    pdf.add_blank_page(width=72, height=72)
    pdf.encrypt("test-password")
    encrypted = BytesIO()
    pdf.write(encrypted)
    assert upload(ingestion, "pdf", data=encrypted.getvalue()).status_code == 415
    many = PdfWriter()
    for _ in range(ingestion.settings.max_pdf_pages + 1):
        many.add_blank_page(width=72, height=72)
    output = BytesIO()
    many.write(output)
    assert upload(ingestion, "pdf", data=output.getvalue()).status_code == 415


def test_upload_size_limit_for_file_and_streamed_body(ingestion):
    ingestion.settings.max_upload_bytes = 20
    assert upload(ingestion).status_code == 413
    assert upload(ingestion, data=b"x" * (65 * 1024)).status_code == 413
    assert_no_canonical(ingestion)


def test_upload_authentication_ownership_and_private_access(ingestion):
    env = ingestion
    assert upload(env, headers={}).status_code == 401
    alice = upload(env).json()["data"]
    assert env.client.get(f"/api/v1/receipts/{alice['id']}", headers=BOB).status_code == 404
    assert env.client.get("/api/v1/receipts", headers=BOB).json()["data"] == []
    assert upload(env, headers=BOB).status_code == 202
    env.dispatcher.dispatch_once()
    with env.factory() as session:
        purchases = list(session.scalars(select(Purchase)))
        assert len(purchases) == 2 and purchases[0].user_id != purchases[1].user_id
        assert session.scalar(select(func.count()).select_from(Merchant)) == 1
    # M10 exposes the private original to its owner; foreign access stays hidden.
    assert env.client.get(f"/api/v1/receipts/{alice['id']}/file", headers=ALICE).status_code == 200
    assert env.client.get(f"/api/v1/receipts/{alice['id']}/file", headers=BOB).status_code == 404


def test_unknown_form_fields_and_multiple_files_are_rejected(ingestion):
    client = ingestion.client
    file = ("file", ("image.png", document(), "image/png"))
    assert client.post("/api/v1/receipts", headers=ALICE, files=[file, file]).status_code == 422
    assert (
        client.post(
            "/api/v1/receipts", headers=ALICE, files=[file], data={"user_id": str(uuid4())}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/v1/receipts?user_id=other", headers=ALICE, files=[file]).status_code
        == 422
    )


def test_duplicate_upload_returns_conflict_and_does_not_replace_artifact(ingestion):
    first = upload(ingestion).json()["data"]
    assert upload(ingestion, filename="renamed.png").status_code == 409
    assert len(list(ingestion.storage.root.iterdir())) == 1
    assert (
        ingestion.client.get(f"/api/v1/receipts/{first['id']}", headers=ALICE).json()["data"][
            "original_filename"
        ]
        == "receipt.png"
    )


def test_concurrent_duplicate_uploads_create_one_artifact(ingestion):
    env = ingestion
    me = env.client.get("/api/v1/me", headers=ALICE).json()["data"]
    current = CurrentUser(UUID(me["id"]), me["firebase_uid"])

    def execute(_):
        with env.factory() as session:
            try:
                return (
                    UploadService(session, current, env.storage, env.settings)
                    .upload(Upload("receipt.png", "image/png", document()))
                    .id
                )
            except Conflict:
                return None

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(execute, range(4)))
    assert sum(result is not None for result in results) == 1
    assert len(list(env.storage.root.iterdir())) == 1


def test_failed_storage_upload_can_be_retried_without_duplicate_metadata(ingestion, monkeypatch):
    env = ingestion
    original = env.storage.put_object
    monkeypatch.setattr(
        env.storage, "put_object", lambda *_: (_ for _ in ()).throw(StorageUnavailable())
    )
    assert upload(env).status_code == 503
    failed = env.client.get("/api/v1/receipts", headers=ALICE).json()["data"][0]
    assert failed["status"] == "FAILED" and failed["failure_code"] == "upload_storage_failed"
    monkeypatch.setattr(env.storage, "put_object", original)
    retry = upload(env)
    assert retry.status_code == 202 and retry.json()["data"]["id"] == failed["id"]
    env.dispatcher.dispatch_once()
    assert len(env.extractor.calls) == 1


def test_expired_upload_reservation_is_recoverable(ingestion):
    env = ingestion
    me = env.client.get("/api/v1/me", headers=ALICE).json()["data"]
    current = CurrentUser(UUID(me["id"]), me["firebase_uid"])
    data = validate_upload(Upload("receipt.png", "image/png", document()), env.settings)
    with env.factory.begin() as session:
        reserved = UploadRepository(session, current).reserve(
            data, env.clock() - timedelta(minutes=10), 300
        )
    assert upload(env).json()["data"]["id"] == str(reserved.receipt_id)


@pytest.mark.parametrize(
    "output,code",
    [
        ("not json", "extraction_schema_invalid"),
        (json.dumps(evidence(grand_total="-1")), "extraction_schema_invalid"),
        (json.dumps(evidence(purchase_date="2026-02-30")), "extraction_schema_invalid"),
        (json.dumps(evidence(purchase_time=None)), "purchase_time_missing"),
        (json.dumps(evidence(confidence=0.2)), "confidence_insufficient"),
        (json.dumps(evidence(grand_total="12")), "financial_validation"),
        (json.dumps(evidence(subtotal="12")), "line_totals_conflict"),
    ],
)
def test_invalid_extraction_enters_review_without_canonical_writes(ingestion, output, code):
    env = ingestion
    env.extractor.output = output
    receipt = upload(env).json()["data"]
    env.dispatcher.dispatch_once()
    result = env.client.get(f"/api/v1/receipts/{receipt['id']}", headers=ALICE).json()["data"]
    assert result["status"] == "NEEDS_REVIEW" and result["failure_code"] == code
    assert result["purchase_id"] is None
    assert_no_canonical(env)
    with env.factory() as session:
        run = session.scalars(select(ExtractionRun)).one()
        assert run.status == "FAILED" and run.error_code == code and run.completed_at
        assert run.raw_output["text"] == output
    assert env.dispatcher.dispatch_once() == 0


def test_provider_timeout_is_retried_after_backoff_then_succeeds(ingestion):
    env = ingestion
    env.extractor.error = ProcessingError(
        "provider_timeout", "Extraction provider timed out.", retryable=True
    )
    receipt = upload(env).json()["data"]
    env.dispatcher.dispatch_once()
    task = event_task(env, receipt["id"])
    env.processor.process(task)
    assert len(env.extractor.calls) == 1  # Retry is not yet due.
    env.extractor.error = None
    env.offset = timedelta(seconds=6)
    env.dispatcher.dispatch_once()
    result = env.client.get(f"/api/v1/receipts/{receipt['id']}", headers=ALICE).json()["data"]
    assert result["status"] == "PROCESSED" and result["attempt_count"] == 2
    with env.factory() as session:
        assert sorted(session.scalars(select(ExtractionRun.status))) == ["FAILED", "SUCCEEDED"]


def test_retry_exhaustion_preserves_artifact_and_requires_explicit_retry(ingestion):
    env = ingestion
    env.extractor.error = ProcessingError("provider_timeout", "Timeout.", retryable=True)
    receipt = upload(env).json()["data"]
    for _ in range(env.settings.receipt_max_attempts):
        env.dispatcher.dispatch_once()
        env.offset += timedelta(minutes=1)
    assert env.dispatcher.dispatch_once() == 0
    assert len(env.extractor.calls) == env.settings.receipt_max_attempts
    assert_no_canonical(env)
    with env.factory() as session:
        row = session.get(Receipt, UUID(receipt["id"]))
        assert row.status == "FAILED" and env.storage.get_object(row.storage_uri)
    env.extractor.error = None
    env.processor.retry(UUID(receipt["id"]))
    env.dispatcher.dispatch_once()
    with env.factory() as session:
        assert session.scalar(select(func.count()).select_from(ExtractionRun)) == 4
        assert session.get(Receipt, UUID(receipt["id"])).status == "PROCESSED"


def test_permanent_provider_failure_stops_without_blind_retry(ingestion):
    env = ingestion
    env.extractor.error = ProcessingError(
        "provider_configuration", "Provider configuration unavailable."
    )
    receipt = upload(env).json()["data"]
    env.dispatcher.dispatch_once()
    env.offset = timedelta(days=1)
    assert env.dispatcher.dispatch_once() == 0
    assert (
        env.client.get(f"/api/v1/receipts/{receipt['id']}", headers=ALICE).json()["data"]["status"]
        == "FAILED"
    )
    assert_no_canonical(env)


def test_duplicate_worker_delivery_is_idempotent(ingestion):
    receipt = upload(ingestion).json()["data"]
    task = event_task(ingestion, receipt["id"])
    ingestion.processor.process(task)
    ingestion.processor.process(task)
    with ingestion.factory() as session:
        assert session.scalar(select(func.count()).select_from(Purchase)) == 1
        assert session.scalar(select(func.count()).select_from(ExtractionRun)) == 1
    assert len(ingestion.extractor.calls) == 1


@pytest.mark.parametrize("expire", [False, True])
def test_concurrent_worker_and_expired_lease_cannot_commit_twice(ingestion, expire):
    env = ingestion
    receipt = upload(env).json()["data"]
    task = event_task(env, receipt["id"])
    started, release = Event(), Event()

    class BlockingExtractor(FakeExtractor):
        def extract(self, *args):
            result = super().extract(*args)
            if len(self.calls) == 1:
                started.set()
                assert release.wait(timeout=30)
            return result

    extractor = BlockingExtractor()
    env.processor.extractor = extractor
    with ThreadPoolExecutor(max_workers=1) as executor:
        work = executor.submit(env.processor.process, task)
        try:
            assert started.wait(timeout=30)
            if expire:
                env.offset = timedelta(seconds=400)
            env.processor.process(task)
        finally:
            release.set()
        work.result(timeout=30)
    with env.factory() as session:
        assert session.scalar(select(func.count()).select_from(Purchase)) == 1
        runs = list(session.scalars(select(ExtractionRun)))
        assert sum(run.status == "SUCCEEDED" for run in runs) == 1
        if expire:
            assert len(runs) == 2 and any(run.error_code == "worker_lease_expired" for run in runs)
        else:
            assert len(runs) == 1


def test_rollback_after_canonical_event_write_then_recovery(ingestion, monkeypatch):
    env = ingestion
    receipt = upload(env).json()["data"]
    original = OutboxRepository.record_purchase_created

    def fail_after_event(self, purchase_id):
        original(self, purchase_id)
        raise OperationalError("redacted", {}, Exception("simulated database failure"))

    monkeypatch.setattr(OutboxRepository, "record_purchase_created", fail_after_event)
    env.dispatcher.dispatch_once()
    assert_no_canonical(env)
    with env.factory() as session:
        assert session.get(Receipt, UUID(receipt["id"])).status == "FAILED"
        assert session.scalars(select(ExtractionRun)).one().status == "FAILED"
    monkeypatch.setattr(OutboxRepository, "record_purchase_created", original)
    env.offset = timedelta(seconds=6)
    env.dispatcher.dispatch_once()
    with env.factory() as session:
        assert session.scalar(select(func.count()).select_from(Purchase)) == 1


def test_catalog_normalization_maps_only_existing_categories_and_justified_products(ingestion):
    env = ingestion
    me = env.client.get("/api/v1/me", headers=ALICE).json()["data"]
    with env.factory() as session:
        category = PurchaseService(
            session, CurrentUser(UUID(me["id"]), me["firebase_uid"])
        ).create_category(CategoryCreate(name="Test category", slug="test-category"))
    data = evidence(
        category_suggestion="test-category",
        line_items=[
            {
                "raw_name": "Test product",
                "line_total": "10.50",
                "category_suggestion": "Test category",
                "product": {
                    "name": "Observed product",
                    "gtin": "4006381333931",
                    "source": "OBSERVED",
                    "confidence": 0.99,
                },
            }
        ],
    )
    env.extractor.output = json.dumps(data)
    upload(env)
    env.dispatcher.dispatch_once()
    upload(env, "jpg")
    env.dispatcher.dispatch_once()
    with env.factory() as session:
        assert session.scalar(select(func.count()).select_from(Merchant)) == 1
        assert session.scalar(select(func.count()).select_from(Product)) == 1
        assert session.scalar(select(func.count()).select_from(Category)) == 1
        assert all(
            item.category_id == category.id and item.product_id
            for item in session.scalars(select(LineItem))
        )


def test_uncertain_product_and_unknown_category_are_not_created(ingestion):
    env = ingestion
    env.extractor.output = json.dumps(
        evidence(
            category_suggestion="invented taxonomy",
            line_items=[
                {
                    "raw_name": "Item",
                    "line_total": "10.50",
                    "category_suggestion": "invented category",
                    "product": {
                        "name": "Guessed product",
                        "gtin": "4006381333931",
                        "source": "INFERRED",
                        "confidence": 0.99,
                    },
                }
            ],
        )
    )
    upload(env)
    env.dispatcher.dispatch_once()
    with env.factory() as session:
        assert session.scalar(select(func.count()).select_from(Product)) == 0
        assert session.scalar(select(func.count()).select_from(Category)) == 0
        item = session.scalars(select(LineItem)).one()
        assert item.product_id is item.category_id is None


def test_artifact_tampering_never_reaches_model(ingestion, monkeypatch):
    env = ingestion
    receipt = upload(env).json()["data"]
    monkeypatch.setattr(env.storage, "get_object", lambda _: b"altered")
    env.dispatcher.dispatch_once()
    assert not env.extractor.calls
    result = env.client.get(f"/api/v1/receipts/{receipt['id']}", headers=ALICE).json()["data"]
    assert result["status"] == "FAILED" and result["failure_code"] == "artifact_mismatch"
    assert_no_canonical(env)


def test_upload_event_cannot_reference_other_owners_receipt(ingestion):
    env = ingestion
    receipt = upload(env).json()["data"]
    bob = env.client.get("/api/v1/me", headers=BOB).json()["data"]
    with env.factory() as session:
        with pytest.raises(IntegrityError), session.begin():
            session.execute(
                insert(OutboxEvent).values(
                    user_id=UUID(bob["id"]),
                    receipt_id=UUID(receipt["id"]),
                    event_type="RECEIPT_UPLOADED",
                    payload={},
                )
            )


def test_real_http_smoke_with_local_storage_and_fake_extractor(ingestion):
    env = ingestion
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    address, port = listener.getsockname()
    server = uvicorn.Server(uvicorn.Config(env.client.app, log_level="error"))
    thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://{address}:{port}", timeout=15) as client:
            accepted = client.post(
                "/api/v1/receipts",
                headers=ALICE,
                files={"file": ("receipt.png", document(), "image/png")},
            )
            assert accepted.status_code == 202
            receipt = accepted.json()["data"]
            assert receipt["status"] == "UPLOADED" and env.extractor.calls == []
            env.dispatcher.dispatch_once()
            completed = client.get(f"/api/v1/receipts/{receipt['id']}", headers=ALICE)
            assert completed.status_code == 200
            assert completed.json()["data"]["status"] == "PROCESSED"
            assert completed.json()["data"]["purchase_id"]
            print("Local HTTP smoke passed: 202 UPLOADED -> 200 PROCESSED with canonical purchase.")
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        listener.close()
        assert not thread.is_alive()


def test_upload_finalization_failure_does_not_emit_a_partial_job(ingestion, monkeypatch):
    env = ingestion
    original = UploadRepository.uploaded

    def fail_after_enqueue(self, *args):
        original(self, *args)
        raise OperationalError("redacted", {}, Exception("simulated commit failure"))

    monkeypatch.setattr(UploadRepository, "uploaded", fail_after_enqueue)
    assert upload(env).status_code == 503
    with env.factory.begin() as session:
        row = session.scalars(select(Receipt)).one()
        assert row.status == "PENDING_UPLOAD" and row.storage_uri is None
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 0
        receipt_id = row.id
        row.lease_expires_at = env.clock() - timedelta(seconds=1)
    monkeypatch.setattr(UploadRepository, "uploaded", original)
    assert upload(env).json()["data"]["id"] == str(receipt_id)
    env.dispatcher.dispatch_once()
    with env.factory() as session:
        assert session.get(Receipt, receipt_id).status == "PROCESSED"


def test_transient_storage_read_failure_and_review_can_be_retried(ingestion, monkeypatch):
    env = ingestion
    receipt = upload(env).json()["data"]
    original = env.storage.get_object

    def unavailable(_):
        raise StorageUnavailable

    monkeypatch.setattr(env.storage, "get_object", unavailable)
    env.dispatcher.dispatch_once()
    assert not env.extractor.calls
    monkeypatch.setattr(env.storage, "get_object", original)
    env.extractor.output = json.dumps(evidence(confidence=0.1))
    env.offset = timedelta(seconds=6)
    env.dispatcher.dispatch_once()
    assert (
        env.client.get(f"/api/v1/receipts/{receipt['id']}", headers=ALICE).json()["data"]["status"]
        == "NEEDS_REVIEW"
    )
    env.extractor.output = json.dumps(evidence())
    env.processor.retry(UUID(receipt["id"]))
    env.dispatcher.dispatch_once()
    with env.factory() as session:
        assert session.get(Receipt, UUID(receipt["id"])).status == "PROCESSED"
        assert session.scalar(select(func.count()).select_from(ExtractionRun)) == 3
    with pytest.raises(Conflict):
        env.processor.retry(UUID(receipt["id"]))


@pytest.mark.parametrize("kind", ["png", "pdf"])
def test_owned_original_file_is_private_and_validated(ingestion, kind, monkeypatch):
    env = ingestion
    receipt = upload(env, kind, filename=f"original receipt.{kind}").json()["data"]
    path = f"/api/v1/receipts/{receipt['id']}/file"
    reads = []
    original = env.storage.get_object

    def read(reference):
        reads.append(reference)
        return original(reference)

    monkeypatch.setattr(env.storage, "get_object", read)
    assert env.client.get(path).status_code == 401
    assert env.client.get(path, headers=BOB).status_code == 404
    assert env.client.get(f"/api/v1/receipts/{uuid4()}/file", headers=ALICE).status_code == 404
    assert reads == []
    response = env.client.get(path, headers=ALICE)
    assert response.status_code == 200
    assert response.content == document(kind)
    assert response.headers["content-type"] == receipt["mime_type"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "original%20receipt" in response.headers["content-disposition"]
    assert len(reads) == 1
    assert env.client.get(path + "?user_id=alice", headers=ALICE).status_code == 422
    monkeypatch.setattr(env.storage, "get_object", lambda reference: b"corrupted")
    assert env.client.get(path, headers=ALICE).status_code == 503


def test_original_file_rejects_metadata_without_upload(ingestion):
    response = ingestion.client.post(
        "/api/v1/receipts",
        headers=ALICE,
        json={
            "original_filename": "pending.png",
            "mime_type": "image/png",
            "file_size": 100,
            "content_hash": "a" * 64,
            "source": "USER_UPLOAD",
        },
    )
    assert response.status_code == 201
    receipt_id = response.json()["data"]["id"]
    assert (
        ingestion.client.get(f"/api/v1/receipts/{receipt_id}/file", headers=ALICE).status_code
        == 404
    )
