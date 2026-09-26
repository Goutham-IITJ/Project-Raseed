import json
import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier, Thread
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
import uvicorn
from conftest import FakeVerifier
from fastapi.testclient import TestClient
from ingestion_fixtures import FakeExtractor, document, evidence
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError
from test_purchase_validation import purchase_data

from backend.app.config import Settings
from backend.app.database import make_session_factory
from backend.app.identity.context import CurrentUser
from backend.app.ingestion.service import LocalTaskQueue, OutboxDispatcher, ReceiptProcessor
from backend.app.ingestion.storage import LocalStorageProvider
from backend.app.inventory.models import InventoryEvent, InventoryItem, InventoryLot
from backend.app.inventory.repository import InventoryRepository
from backend.app.inventory.schemas import EvidenceCorrection
from backend.app.inventory.service import InventoryService
from backend.app.inventory.worker import (
    InventoryDispatcher,
    InventoryProcessor,
    LocalInventoryTaskQueue,
    PurchaseTask,
)
from backend.app.main import create_app
from backend.app.purchases.errors import Conflict, DomainError, NotFound
from backend.app.purchases.models import OutboxEvent, Purchase
from backend.app.purchases.schemas import CategoryCreate, ProductCreate, PurchaseCreate
from backend.app.purchases.service import PurchaseService

pytestmark = pytest.mark.integration
ALICE = {"Authorization": "Bearer alice-token"}
BOB = {"Authorization": "Bearer bob-token"}


@pytest.fixture
def inventory(database, tmp_path):
    factory = make_session_factory(database)
    settings = Settings(firebase_project_id="test", local_storage_path=tmp_path / "private")
    storage = LocalStorageProvider(settings.local_storage_path)
    env = SimpleNamespace(factory=factory, settings=settings, storage=storage, offset=timedelta())
    env.clock = lambda: datetime.now(timezone.utc) + env.offset
    env.processor = InventoryProcessor(factory, clock=env.clock)
    env.dispatcher = InventoryDispatcher(
        factory, LocalInventoryTaskQueue(env.processor), clock=env.clock
    )
    app = create_app(settings, verifier=FakeVerifier(), session_factory=factory, storage=storage)
    with TestClient(app) as client:
        env.client = client
        for name, headers in (("alice", ALICE), ("bob", BOB)):
            profile = client.get("/api/v1/me", headers=headers).json()["data"]
            setattr(env, name, CurrentUser(UUID(profile["id"]), profile["firebase_uid"]))
        yield env


def category(env, **changes):
    with env.factory() as session:
        return PurchaseService(session, env.alice).create_category(
            CategoryCreate.model_validate(
                {
                    "name": "Fixture stock",
                    "slug": f"fixture-{uuid4()}",
                    "inventory_eligible": True,
                    **changes,
                }
            )
        )


def product(env, **changes):
    with env.factory() as session:
        return PurchaseService(session, env.alice).create_product(
            ProductCreate.model_validate(
                {
                    "canonical_name": "Fixture product",
                    **changes,
                }
            )
        )


def purchase(env, *, owner=None, lines=None):
    with env.factory() as session:
        return PurchaseService(session, owner or env.alice).create_purchase(
            PurchaseCreate.model_validate(
                purchase_data(
                    line_items=lines
                    if lines is not None
                    else [
                        {
                            "raw_name": "Milk",
                            "quantity": "2",
                            "unit": "each",
                        }
                    ]
                )
            )
        )


def task(env, purchase_id):
    with env.factory() as session:
        return PurchaseTask(
            session.scalars(
                select(OutboxEvent.id).where(
                    OutboxEvent.purchase_id == purchase_id,
                    OutboxEvent.event_type == "PURCHASE_CREATED",
                )
            ).one()
        )


def enroll(env, line_id, **changes):
    return env.client.post(
        "/api/v1/inventory/lots",
        headers=ALICE,
        json={
            "idempotency_key": str(uuid4()),
            "line_item_id": str(line_id),
            "quantity": "2",
            "unit": "each",
            "reason": "Confirmed physical stock",
            **changes,
        },
    )


def lot(env):
    purchased = purchase(env)
    response = enroll(env, purchased.line_items[0].id)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def change(env, stock, **changes):
    return env.client.post(
        f"/api/v1/inventory/lots/{stock['id']}/events",
        headers=ALICE,
        json={
            "idempotency_key": str(uuid4()),
            "expected_version": stock["version"],
            "event_type": "CONSUMED",
            "quantity": "1",
            "reason": "Used at home",
            **changes,
        },
    )


def test_purchase_delivery_creates_owned_ledger_and_atomic_outbox(inventory):
    env = inventory
    cat = category(env)
    purchased = purchase(
        env, lines=[{"raw_name": "Milk", "quantity": "2.5", "unit": " KG ", "category_id": cat.id}]
    )
    assert env.client.get("/api/v1/inventory/lots", headers=ALICE).json()["data"] == []
    assert env.dispatcher.dispatch_once() == 1
    assert env.dispatcher.dispatch_once() == 0
    stocks = env.client.get("/api/v1/inventory/lots", headers=ALICE).json()["data"]
    assert len(stocks) == 1
    stock = stocks[0]
    assert stock["purchase_id"] == str(purchased.id) and stock["unit"] == "kg"
    assert Decimal(stock["quantity_remaining"]) == Decimal("2.5")
    assert Decimal(stock["quantity_acquired"]) == Decimal("2.5")
    assert stock["expiry"] == {
        "date": None,
        "source": "UNKNOWN",
        "confidence": None,
        "provenance": "UNKNOWN",
        "status": "UNKNOWN",
    }
    assert "user_id" not in stock
    with env.factory() as session:
        event = session.scalars(select(InventoryEvent)).one()
        assert event.user_id == env.alice.id and event.source == "PURCHASE"
        assert event.actor == "INVENTORY_WORKER" and event.actor_user_id is None
        changed = session.scalars(
            select(OutboxEvent).where(OutboxEvent.event_type == "INVENTORY_CHANGED")
        ).one()
        assert changed.inventory_event_id == event.id and changed.user_id == env.alice.id
        assert changed.published_at is None and changed.payload["lot_id"] == stock["id"]
        assert session.get(OutboxEvent, task(env, purchased.id).event_id).published_at is not None
    env.processor.process(task(env, purchased.id))
    history = env.client.get(f"/api/v1/inventory/lots/{stock['id']}/events", headers=ALICE).json()[
        "data"
    ]
    assert len(history) == 1 and history[0]["event_type"] == "PURCHASED"


@pytest.mark.parametrize(
    "flag,quantity,unit,reason",
    [
        (None, "2", "each", "UNKNOWN_ELIGIBILITY"),
        (False, "2", "each", "EXCLUDED"),
        (True, None, "each", "MISSING_QUANTITY"),
        (True, "2", None, "MISSING_UNIT"),
        (True, "2", " ", "MISSING_UNIT"),
    ],
)
def test_eligibility_skips_unknowns_without_inventing_stock(
    inventory, flag, quantity, unit, reason
):
    env = inventory
    cat = category(env, inventory_eligible=flag)
    purchased = purchase(
        env, lines=[{"raw_name": "Line", "quantity": quantity, "unit": unit, "category_id": cat.id}]
    )
    candidate = env.client.get(
        f"/api/v1/purchases/{purchased.id}/inventory-candidates", headers=ALICE
    ).json()["data"][0]
    assert candidate["reason"] == reason and not candidate["eligible"]
    env.dispatcher.dispatch_once()
    assert env.client.get("/api/v1/inventory/lots", headers=ALICE).json()["data"] == []
    # Explicit confirmation may track it without mutating the uncertain purchase.
    assert enroll(env, purchased.line_items[0].id).status_code == 201
    assert (
        env.client.get(
            f"/api/v1/purchases/{purchased.id}/inventory-candidates", headers=ALICE
        ).json()["data"][0]["reason"]
        == "ALREADY_TRACKED"
    )


def test_eligibility_inheritance_product_override_and_empty_purchase(inventory):
    env = inventory
    parent = category(env)
    child = category(env, parent_id=parent.id, inventory_eligible=None)
    excluded = product(env, category_id=child.id, inventory_eligible=False)
    inherited = product(env, category_id=child.id)
    purchased = purchase(
        env,
        lines=[
            {"raw_name": "Excluded", "quantity": "1", "unit": "each", "product_id": excluded.id},
            {"raw_name": "Included", "quantity": "1", "unit": "each", "product_id": inherited.id},
        ],
    )
    decisions = env.client.get(
        f"/api/v1/purchases/{purchased.id}/inventory-candidates", headers=ALICE
    ).json()["data"]
    by_name = {d["raw_name"]: d for d in decisions}
    assert (
        by_name["Excluded"]["reason"] == "EXCLUDED"
        and by_name["Excluded"]["eligibility_source"] == "PRODUCT"
    )
    assert (
        by_name["Included"]["reason"] == "ELIGIBLE"
        and by_name["Included"]["eligibility_source"] == "CATEGORY"
    )
    purchase(env, lines=[])
    assert env.dispatcher.dispatch_once() == 2
    assert len(env.client.get("/api/v1/inventory/lots", headers=ALICE).json()["data"]) == 1


def test_only_same_product_and_unit_merge_across_purchases(inventory):
    env = inventory
    known = product(env, inventory_eligible=True)
    for unit in ["each", " EACH ", "kg"]:
        purchase(
            env,
            lines=[{"raw_name": "Label", "quantity": "2", "unit": unit, "product_id": known.id}],
        )
    env.dispatcher.dispatch_once()
    for _ in range(2):
        unknown = purchase(env)
        enroll(env, unknown.line_items[0].id)
    items = env.client.get("/api/v1/inventory/items", headers=ALICE).json()["data"]
    assert len(items) == 4
    merged = next(item for item in items if item["lot_count"] == 2)
    assert merged["unit"] == "each" and Decimal(merged["quantity_remaining"]) == 4
    related = env.client.get(f"/api/v1/inventory/items/{merged['id']}/lots", headers=ALICE).json()[
        "data"
    ]
    assert len(related) == 2
    assert (
        env.client.get(f"/api/v1/inventory/items/{merged['id']}", headers=ALICE).json()["data"]
        == merged
    )


@pytest.mark.parametrize("event_type", ["CONSUMED", "EXPIRED", "DISCARDED", "RETURNED"])
def test_removals_and_replay_leave_purchase_history_unchanged(inventory, event_type):
    env = inventory
    stock = lot(env)
    key = str(uuid4())
    first = change(env, stock, event_type=event_type, quantity="0.125", idempotency_key=key)
    assert first.status_code == 201, first.text
    repeated = change(env, stock, event_type=event_type, quantity="0.125", idempotency_key=key)
    assert repeated.status_code == 201 and repeated.json() == first.json()
    assert change(env, stock, quantity="0.25", idempotency_key=key).status_code == 409
    assert change(env, stock).status_code == 409  # stale version
    updated = env.client.get(f"/api/v1/inventory/lots/{stock['id']}", headers=ALICE).json()["data"]
    assert updated["version"] == 2 and Decimal(updated["quantity_remaining"]) == Decimal("1.875")
    purchased = env.client.get(f"/api/v1/purchases/{stock['purchase_id']}", headers=ALICE).json()[
        "data"
    ]
    assert Decimal(purchased["line_items"][0]["quantity"]) == 2
    assert change(env, updated, quantity="2").status_code == 409


def test_adjustments_and_absolute_corrections_are_auditable(inventory):
    env = inventory
    stock = lot(env)
    adjusted = change(
        env, stock, event_type="MANUAL_ADJUSTMENT", quantity=None, quantity_delta="0.5"
    )
    assert adjusted.status_code == 201
    stock["version"] = 2
    corrected = change(env, stock, event_type="CORRECTION", quantity=None, quantity_remaining="0")
    assert corrected.status_code == 201 and Decimal(
        corrected.json()["data"]["quantity_delta"]
    ) == Decimal("-2.5")
    state = env.client.get(f"/api/v1/inventory/lots/{stock['id']}", headers=ALICE).json()["data"]
    assert Decimal(state["quantity_remaining"]) == 0 and Decimal(state["quantity_acquired"]) == 2
    assert (
        change(
            env, state, event_type="MANUAL_ADJUSTMENT", quantity=None, quantity_delta="-1"
        ).status_code
        == 409
    )
    assert (
        change(
            env, state, event_type="CORRECTION", quantity=None, quantity_remaining="1"
        ).status_code
        == 201
    )
    history = env.client.get(f"/api/v1/inventory/lots/{stock['id']}/events", headers=ALICE).json()[
        "data"
    ]
    assert [h["sequence"] for h in history] == [4, 3, 2, 1]
    assert all(h["actor"] == "USER" and h["source"] == "USER" for h in history)


def test_manual_duplicate_line_key_scope_and_retry_of_successful_enrollment(inventory):
    env = inventory
    purchased = purchase(env)
    key = str(uuid4())
    first = enroll(env, purchased.line_items[0].id, idempotency_key=key)
    assert first.status_code == 201
    assert enroll(env, purchased.line_items[0].id, idempotency_key=key).json() == first.json()
    assert enroll(env, purchased.line_items[0].id).status_code == 409
    assert (
        enroll(env, purchased.line_items[0].id, quantity="3", idempotency_key=key).status_code
        == 409
    )
    other = purchase(env)
    assert enroll(env, other.line_items[0].id, idempotency_key=key).status_code == 409
    env.dispatcher.dispatch_once()
    assert len(env.client.get("/api/v1/inventory/lots", headers=ALICE).json()["data"]) == 1


@pytest.mark.parametrize(
    "source,provenance",
    [("RECEIPT", "OBSERVED"), ("PRODUCT_KNOWLEDGE", "EXTERNAL"), ("MODEL_ESTIMATE", "INFERRED")],
)
def test_expiry_provenance_and_user_override_preserve_history(inventory, source, provenance):
    env = inventory
    stock = lot(env)
    data = EvidenceCorrection.model_validate(
        {
            "idempotency_key": uuid4(),
            "expected_version": 1,
            "reason": "Evidence fixture",
            "expiry": {"date": "2026-09-25", "source": source, "confidence": "0.7"},
        }
    )
    with env.factory() as session:
        service = InventoryService(
            session, env.alice, clock=lambda: datetime(2026, 9, 24, 20, tzinfo=timezone.utc)
        )
        first = service.record_expiry_evidence(UUID(stock["id"]), data)
        assert service.record_expiry_evidence(UUID(stock["id"]), data) == first
        current = service.get_lot(UUID(stock["id"]))
        assert current.expiry.status == "DUE"  # Kolkata is already Sep 25
        assert current.expiry.provenance == provenance and current.quantity_remaining == 2
    stock["version"] = 2
    override = change(
        env,
        stock,
        event_type="CORRECTION",
        quantity=None,
        expiry={"date": "2026-10-01", "source": "USER", "confidence": "1"},
    )
    assert override.status_code == 201
    stock["version"] = 3
    assert change(env, stock, event_type="CORRECTION", quantity=None, expiry={}).status_code == 201
    current = env.client.get(f"/api/v1/inventory/lots/{stock['id']}", headers=ALICE).json()["data"]
    assert current["expiry"]["source"] == "UNKNOWN" and current["expiry"]["date"] is None
    history = env.client.get(f"/api/v1/inventory/lots/{stock['id']}/events", headers=ALICE).json()[
        "data"
    ]
    assert history[2]["expiry"]["source"] == source and history[1]["expiry"]["source"] == "USER"


def test_past_due_expiry_never_silently_depletes_stock(inventory):
    env = inventory
    purchased = purchase(env)
    stock = enroll(
        env,
        purchased.line_items[0].id,
        expiry={"date": "2020-01-01", "source": "USER", "confidence": "1"},
    ).json()["data"]
    assert stock["expiry"]["status"] == "PAST_DUE" and stock["expiry"]["provenance"] == "OBSERVED"
    assert Decimal(stock["quantity_remaining"]) == 2
    assert change(env, stock, event_type="EXPIRED", quantity="2").status_code == 201


def test_owned_apis_hide_other_users_and_reject_extra_parameters(inventory):
    env = inventory
    stock = lot(env)
    paths = [
        f"/inventory/lots/{stock['id']}",
        f"/inventory/lots/{stock['id']}/events",
        f"/inventory/items/{stock['item_id']}",
        f"/inventory/items/{stock['item_id']}/lots",
        f"/purchases/{stock['purchase_id']}/inventory-candidates",
    ]
    for path in paths:
        assert env.client.get("/api/v1" + path, headers=BOB).status_code == 404
        assert env.client.get("/api/v1" + path).status_code == 401
        assert env.client.get("/api/v1" + path + "?user_id=x", headers=ALICE).status_code == 422
    for path in ["/inventory/items", "/inventory/lots"]:
        response = env.client.get("/api/v1" + path, headers=BOB)
        assert response.json()["data"] == [] and response.headers["cache-control"] == "no-store"
        assert env.client.get("/api/v1" + path + "?limit=101", headers=ALICE).status_code == 422
    body = {
        "idempotency_key": str(uuid4()),
        "line_item_id": stock["line_item_id"],
        "quantity": "1",
        "unit": "each",
        "reason": "Test",
    }
    assert env.client.post("/api/v1/inventory/lots", headers=BOB, json=body).status_code == 404
    assert env.client.post("/api/v1/inventory/lots", json=body).status_code == 401
    response = env.client.post(
        f"/api/v1/inventory/lots/{stock['id']}/events",
        headers=BOB,
        json={
            "idempotency_key": str(uuid4()),
            "expected_version": 1,
            "event_type": "CONSUMED",
            "quantity": "1",
            "reason": "Test",
        },
    )
    assert response.status_code == 404
    assert env.client.get(f"/api/v1/inventory/lots/{uuid4()}", headers=ALICE).status_code == 404
    assert env.client.get("/api/v1/inventory/lots/not-a-uuid", headers=ALICE).status_code == 422


def test_concurrent_duplicate_workers_and_competing_user_removals(inventory):
    env = inventory
    known = product(env, inventory_eligible=True)
    purchased = purchase(
        env, lines=[{"raw_name": "Stock", "quantity": "2", "unit": "each", "product_id": known.id}]
    )
    job = task(env, purchased.id)
    barrier = Barrier(2)

    def run_worker(_):
        barrier.wait(timeout=10)
        env.processor.process(job)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run_worker, range(2)))
    stock = env.client.get("/api/v1/inventory/lots", headers=ALICE).json()["data"][0]

    def remove(_):
        barrier.wait(timeout=10)
        return change(env, stock, quantity="2").status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(remove, range(2))) == [201, 409]
    current = env.client.get(f"/api/v1/inventory/lots/{stock['id']}", headers=ALICE).json()["data"]
    assert current["version"] == 2 and Decimal(current["quantity_remaining"]) == 0


def test_rollback_retry_exhaustion_and_explicit_recovery(inventory, monkeypatch):
    env = inventory
    known = product(env, inventory_eligible=True)
    purchased = purchase(
        env,
        lines=[{"raw_name": "Stock", "quantity": "2", "unit": "each", "product_id": known.id}] * 2,
    )
    original = InventoryRepository.append

    def fail_after_append(self, event):
        original(self, event)
        raise OperationalError("redacted", {}, Exception("simulated failure"))

    monkeypatch.setattr(InventoryRepository, "append", fail_after_append)
    for delay in [0, 6, 17]:
        env.offset = timedelta(seconds=delay)
        assert env.dispatcher.dispatch_once() == 1
        assert env.dispatcher.dispatch_once() == 0
        with env.factory() as session:
            for model in (InventoryItem, InventoryLot, InventoryEvent):
                assert session.scalar(select(func.count()).select_from(model)) == 0
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(OutboxEvent)
                    .where(OutboxEvent.event_type == "INVENTORY_CHANGED")
                )
                == 0
            )
            assert session.get(Purchase, purchased.id) is not None
    with env.factory() as session:
        event = session.get(OutboxEvent, task(env, purchased.id).event_id)
        assert (
            event.failed_at is not None and event.attempt_count == 3 and event.published_at is None
        )
    monkeypatch.setattr(InventoryRepository, "append", original)
    env.processor.retry(purchased.id)
    assert env.dispatcher.dispatch_once() == 1
    assert len(env.client.get("/api/v1/inventory/lots", headers=ALICE).json()["data"]) == 2
    with pytest.raises(Conflict):
        env.processor.retry(purchased.id)


def test_user_change_rolls_back_with_outbox_failure(inventory, monkeypatch):
    env = inventory
    stock = lot(env)
    original = InventoryRepository.append

    def fail(self, event):
        original(self, event)
        raise OperationalError("redacted", {}, Exception("failed"))

    monkeypatch.setattr(InventoryRepository, "append", fail)
    assert change(env, stock).status_code == 503
    current = env.client.get(f"/api/v1/inventory/lots/{stock['id']}", headers=ALICE).json()["data"]
    assert current == stock
    with env.factory() as session:
        assert session.scalar(select(func.count()).select_from(InventoryEvent)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.event_type == "INVENTORY_CHANGED")
            )
            == 1
        )


def test_concurrent_enrollment_and_owner_scoped_idempotency(inventory):
    env = inventory
    purchased = purchase(env)
    key = str(uuid4())
    barrier = Barrier(2)

    def run(_):
        barrier.wait(timeout=10)
        return enroll(env, purchased.line_items[0].id, idempotency_key=key)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(run, range(2)))
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    bob_purchase = purchase(env, owner=env.bob)
    response = env.client.post(
        "/api/v1/inventory/lots",
        headers=BOB,
        json={
            "idempotency_key": key,
            "line_item_id": str(bob_purchase.line_items[0].id),
            "quantity": "1",
            "unit": "each",
            "reason": "My stock",
        },
    )
    assert response.status_code == 201
    assert response.json()["data"]["item_id"] != first.json()["data"]["item_id"]


def test_terminal_domain_failure_is_not_blindly_retried(inventory, monkeypatch):
    env = inventory
    purchased = purchase(env)

    def invalid(self, purchase_id):
        raise DomainError

    monkeypatch.setattr(InventoryService, "apply_purchase", invalid)
    assert env.dispatcher.dispatch_once() == 1
    env.offset = timedelta(hours=1)
    assert env.dispatcher.dispatch_once() == 0
    with env.factory() as session:
        event = session.get(OutboxEvent, task(env, purchased.id).event_id)
        assert event.attempt_count == 1 and event.failure_code == "inventory_validation_failed"
        assert event.failed_at is not None and event.published_at is None
    with pytest.raises(NotFound):
        env.processor.process(PurchaseTask(uuid4()))
    with pytest.raises(NotFound):
        env.processor.retry(uuid4())


def test_overflow_and_schema_failure_leave_history_intact(inventory):
    env = inventory
    stock = lot(env)
    assert (
        change(
            env,
            stock,
            event_type="MANUAL_ADJUSTMENT",
            quantity=None,
            quantity_delta="99999999999999.999999",
        ).status_code
        == 409
    )
    assert (
        change(
            env,
            stock,
            event_type="CORRECTION",
            quantity=None,
            expiry={"date": "2026-02-30", "source": "USER", "confidence": "1"},
        ).status_code
        == 422
    )
    assert (
        change(
            env,
            stock,
            event_type="CORRECTION",
            quantity=None,
            expiry={"date": "2026-10-01", "source": "MODEL_ESTIMATE", "confidence": "0.8"},
        ).status_code
        == 422
    )
    assert (
        len(
            env.client.get(f"/api/v1/inventory/lots/{stock['id']}/events", headers=ALICE).json()[
                "data"
            ]
        )
        == 1
    )


def test_list_pagination_and_expiry_only_correction_preserve_quantity(inventory):
    env = inventory
    first, second = lot(env), lot(env)
    assert first["id"] != second["id"]
    page1 = env.client.get("/api/v1/inventory/lots?limit=1", headers=ALICE).json()["data"]
    page2 = env.client.get("/api/v1/inventory/lots?limit=1&offset=1", headers=ALICE).json()["data"]
    assert len(page1) == len(page2) == 1 and page1[0]["id"] != page2[0]["id"]
    assert (
        change(
            env,
            first,
            event_type="CORRECTION",
            quantity=None,
            expiry={"date": "2099-12-31", "source": "USER", "confidence": "1"},
        ).status_code
        == 201
    )
    current = env.client.get(f"/api/v1/inventory/lots/{first['id']}", headers=ALICE).json()["data"]
    assert Decimal(current["quantity_remaining"]) == 2 and current["expiry"]["status"] == "NOT_DUE"
    assert (
        env.client.get(
            f"/api/v1/inventory/lots/{first['id']}/events?limit=1&offset=1", headers=ALICE
        ).json()["data"][0]["sequence"]
        == 1
    )


def test_database_rejects_ledger_mutation_and_cross_owner_links(inventory):
    env = inventory
    stock = lot(env)
    with env.factory() as session:
        original = session.scalars(select(InventoryEvent)).one()
        values = {
            column.name: getattr(original, column.name)
            for column in InventoryEvent.__table__.columns
        }
    for sql in ["UPDATE inventory_events SET quantity_delta = 99", "DELETE FROM inventory_events"]:
        with env.factory.begin() as session, pytest.raises(IntegrityError):
            session.execute(text(sql))
    invalid_changes = [
        {"sequence": 4, "event_type": "CONSUMED", "quantity_delta": Decimal(-1)},
        {"sequence": 2, "event_type": "CONSUMED", "quantity_delta": Decimal(-3)},
        {
            "sequence": 2,
            "user_id": env.bob.id,
            "actor_user_id": env.bob.id,
            "event_type": "CONSUMED",
            "quantity_delta": Decimal(-1),
        },
    ]
    for changes in invalid_changes:
        with env.factory.begin() as session, pytest.raises(IntegrityError):
            session.execute(
                insert(InventoryEvent).values(
                    {
                        **values,
                        "id": uuid4(),
                        "idempotency_key": uuid4(),
                        "expiry_changed": False,
                        "expiry_source": None,
                        **changes,
                    }
                )
            )
    with env.factory.begin() as session, pytest.raises(IntegrityError):
        session.execute(
            insert(OutboxEvent).values(
                user_id=env.bob.id,
                inventory_event_id=values["id"],
                event_type="INVENTORY_CHANGED",
                payload={},
            )
        )
    with env.factory.begin() as session, pytest.raises(IntegrityError):
        session.execute(
            update(InventoryLot)
            .where(InventoryLot.id == UUID(stock["id"]))
            .values(user_id=env.bob.id)
        )


def test_local_http_upload_purchase_inventory_and_user_correction(inventory):
    env = inventory
    cat = category(env, name="Fixture groceries", slug="fixture-groceries")
    extracted = evidence()
    extracted["line_items"][0].update(unit="each", category_suggestion=cat.slug)
    extractor = FakeExtractor(json.dumps(extracted))
    processor = ReceiptProcessor(env.factory, env.storage, extractor, env.settings)
    receipts = OutboxDispatcher(env.factory, LocalTaskQueue(processor))
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    address, port = listener.getsockname()
    server = uvicorn.Server(uvicorn.Config(env.client.app, log_level="error"))
    thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://{address}:{port}", timeout=15) as client:
            uploaded = client.post(
                "/api/v1/receipts",
                headers=ALICE,
                files={"file": ("receipt.png", document(), "image/png")},
            )
            assert uploaded.status_code == 202 and not extractor.calls
            assert receipts.dispatch_once() == 1
            receipt = client.get(
                f"/api/v1/receipts/{uploaded.json()['data']['id']}", headers=ALICE
            ).json()["data"]
            assert receipt["status"] == "PROCESSED"
            assert env.dispatcher.dispatch_once() == 1
            stock = client.get("/api/v1/inventory/lots", headers=ALICE).json()["data"][0]
            assert stock["purchase_id"] == receipt["purchase_id"]
            result = client.post(
                f"/api/v1/inventory/lots/{stock['id']}/events",
                headers=ALICE,
                json={
                    "idempotency_key": str(uuid4()),
                    "expected_version": 1,
                    "event_type": "CONSUMED",
                    "quantity": "1",
                    "reason": "Used one",
                },
            )
            assert result.status_code == 201
            item = client.get(f"/api/v1/inventory/items/{stock['item_id']}", headers=ALICE).json()[
                "data"
            ]
            assert Decimal(item["quantity_remaining"]) == 1
            print(
                "Local HTTP smoke: receipt 202 -> canonical purchase -> inventory lot "
                "-> consumption -> balance 1."
            )
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        listener.close()
        assert not thread.is_alive()
