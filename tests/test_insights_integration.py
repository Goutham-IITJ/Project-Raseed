from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal, localcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest
from assistant_fixtures import ScriptedModel, call, calls, final, reference
from fastapi.testclient import TestClient
from m7_fixtures import ALICE, BOB, NOW, app_for, date_at, purchase, spending_fixture
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError

from backend.app.assistant.tools import ToolContext, ToolRegistry
from backend.app.identity.context import VerifiedIdentity
from backend.app.identity.service import provision_user
from backend.app.insights.evaluation import InsightEvaluation
from backend.app.insights.models import Insight
from backend.app.insights.schemas import InsightQuery, InsightUpdate
from backend.app.insights.service import InsightService
from backend.app.insights.worker import (
    InsightDispatcher,
    InsightProcessor,
    InsightTask,
    LocalInsightTaskQueue,
)
from backend.app.inventory.schemas import EventCreate, LotCreate, UserExpiry
from backend.app.inventory.service import InventoryService
from backend.app.inventory.worker import InventoryProcessor, PurchaseTask
from backend.app.purchases.errors import Conflict, NotFound
from backend.app.purchases.models import OutboxEvent

pytestmark = pytest.mark.integration
DEFAULT_EXPIRY = NOW.date() + timedelta(days=1)


def job(env, *, owner=None, lot_id=None, now=NOW):
    with env.factory.begin() as session:
        row = OutboxEvent(
            user_id=(owner or env.alice).id,
            evaluation_lot_id=lot_id,
            schedule_key=str(uuid4()),
            event_type="INSIGHT_EVALUATION_REQUESTED",
            payload={},
            created_at=now,
            available_at=now,
            insight_available_at=now,
        )
        session.add(row)
        session.flush()
        return InsightTask(row.id)


def stock(env, *, expires=DEFAULT_EXPIRY, owner=None):
    owner = owner or env.alice
    bought = purchase(
        env, owner=owner, line_items=[{"raw_name": "Milk", "quantity": "2", "unit": "litre"}]
    )
    with env.factory() as session:
        return InventoryService(session, owner, clock=lambda: NOW).create_lot(
            LotCreate(
                idempotency_key=uuid4(),
                line_item_id=bought.line_items[0].id,
                quantity="2",
                unit="litre",
                reason="Confirmed stock",
                expiry=UserExpiry(date=expires, source="USER", confidence="1")
                if expires is not None
                else UserExpiry(),
            )
        )


def listed(env, *, query=None, now=NOW, owner=None):
    with env.factory() as session:
        return InsightService(session, owner or env.alice, clock=lambda: now).list(
            query or InsightQuery()
        )


def test_financial_rules_are_exact_currency_separated_and_owner_scoped(environment):
    env = environment
    spending_fixture(env)
    for month in [7, 8]:
        for _ in range(3):
            purchase(env, at=date_at(month), amount="500", currency="USD")
    with localcontext() as context:
        context.prec = 3
        candidates = InsightEvaluation(env.factory, env.alice, NOW, "Asia/Kolkata").financial()
    assert {row.type for row in candidates} == {"SPENDING_CHANGE", "UNUSUAL_PURCHASE"}
    spending = next(row for row in candidates if row.type == "SPENDING_CHANGE")
    assert spending.source["metrics"]["currency"] == "INR"
    assert spending.source["metrics"]["current_total"] == "450.000000"
    assert spending.source["metrics"]["comparison_total"] == "300.000000"
    assert spending.source["metrics"]["percentage_change"] == "50.000000"
    unusual = next(row for row in candidates if row.type == "UNUSUAL_PURCHASE")
    assert unusual.source["current"]["largest_purchase"] == "30.000000"
    assert unusual.source["baseline"]["purchase_count"] == 5
    assert unusual.source["baseline"]["total_spent"] == "50.000000"
    assert unusual.source["period"]["start_date"] == "2030-09-25"
    assert unusual.source["baseline_period"]["end_date"] == "2030-09-25"
    assert spending.confidence is None and unusual.confidence is None
    assert InsightEvaluation(env.factory, env.bob, NOW, "Asia/Kolkata").financial() == []


@pytest.mark.parametrize(
    "old,new,count,expected",
    [
        ("100", "125", 3, True),
        ("100", "124.999999", 3, False),
        ("100", "75", 3, True),
        ("100", "75.000001", 3, False),
        ("100", "500", 2, False),
        ("0", "500", 3, False),
    ],
)
def test_spending_thresholds_and_minimum_evidence(environment, old, new, count, expected):
    for _ in range(count):
        purchase(environment, at=date_at(7), amount=old)
        purchase(environment, at=date_at(8), amount=new)
    candidates = InsightEvaluation(
        environment.factory, environment.alice, NOW, "Asia/Kolkata"
    ).financial()
    assert bool(candidates) is expected


@pytest.mark.parametrize(
    "largest,count,expected", [("30", 5, True), ("29.999999", 5, False), ("100", 4, False)]
)
def test_unusual_purchase_threshold_does_not_invent_baseline(environment, largest, count, expected):
    for _ in range(count):
        purchase(environment, at=date_at(9, 5), amount="10")
    purchase(environment, at=date_at(9, 25), amount=largest)
    rows = InsightEvaluation(
        environment.factory, environment.alice, NOW, "Asia/Kolkata"
    ).financial()
    assert any(row.type == "UNUSUAL_PURCHASE" for row in rows) is expected


def test_persisted_insights_have_sources_outbox_and_do_not_steal_inventory_ack(environment):
    env = environment
    spending_fixture(env)
    with env.factory() as session:
        event_id = session.scalar(
            select(OutboxEvent.id).where(
                OutboxEvent.user_id == env.alice.id, OutboxEvent.event_type == "PURCHASE_CREATED"
            )
        )
    task = InsightTask(event_id)
    processor = InsightProcessor(env.factory, clock=lambda: NOW)
    processor.process(task)
    first = listed(env)
    assert len(first) == 2 and all(row.provenance == "DERIVED" for row in first)
    assert all(row.calculation["version"] == "insights.v1" for row in first)
    assert "450.000000" in next(row.summary for row in first if row.type == "SPENDING_CHANGE")
    processor.process(task)
    assert [row.model_dump() for row in listed(env)] == [row.model_dump() for row in first]
    with env.factory() as session:
        event = session.get(OutboxEvent, event_id)
        assert event.insight_processed_at == NOW and event.insight_attempt_count == 1
        assert event.published_at is None and event.attempt_count == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.event_type == "INSIGHT_CREATED")
            )
            == 2
        )
    InventoryProcessor(env.factory, clock=lambda: NOW).process(PurchaseTask(event_id))
    with env.factory() as session:
        event = session.get(OutboxEvent, event_id)
        assert event.published_at == NOW and event.insight_processed_at == NOW


@pytest.mark.parametrize(
    "offset,expected", [(None, False), (4, False), (3, True), (0, True), (-10, True)]
)
def test_inventory_expiry_requires_recorded_date_and_positive_stock(environment, offset, expected):
    env = environment
    lot = stock(env, expires=None if offset is None else NOW.date() + timedelta(days=offset))
    task = job(env, lot_id=lot.id)
    InsightProcessor(env.factory, clock=lambda: NOW).process(task)
    rows = listed(env)
    assert bool(rows) is expected
    if expected:
        row = rows[0]
        assert row.type == "INVENTORY_EXPIRY"
        assert row.confidence == Decimal("1")
        assert row.source_data["lot"]["expiry"]["provenance"] == "OBSERVED"
        assert row.source_data["lot"]["quantity_remaining"] == "2.000000"
        with env.factory() as session:
            InventoryService(session, env.alice, clock=lambda: NOW).record_event(
                lot.id,
                EventCreate(
                    expected_version=1,
                    idempotency_key=uuid4(),
                    event_type="CONSUMED",
                    quantity="2",
                    reason="Used milk",
                ),
            )
            event_id = session.scalar(
                select(OutboxEvent.id)
                .where(OutboxEvent.event_type == "INVENTORY_CHANGED")
                .order_by(OutboxEvent.created_at.desc())
            )
        InsightProcessor(env.factory, clock=lambda: NOW).process(InsightTask(event_id))
        assert listed(env) == []
        assert listed(env, query=InsightQuery(status="RESOLVED"))[0].id == row.id


def test_dismissal_survives_refresh_and_expiry_filters_even_without_worker(environment):
    env = environment
    lot = stock(env)
    processor = InsightProcessor(env.factory, clock=lambda: NOW)
    processor.process(job(env, lot_id=lot.id))
    row = listed(env)[0]
    assert listed(env, now=row.expires_at) == []
    expired = listed(env, now=row.expires_at, query=InsightQuery(status="EXPIRED"))
    assert len(expired) == 1 and expired[0].status == "EXPIRED"
    with env.factory() as session:
        service = InsightService(session, env.alice, clock=lambda: NOW)
        read = service.update(row.id, InsightUpdate(status="READ", expected_version=1))
        assert read.read_at == NOW
        with pytest.raises(Conflict):
            service.update(row.id, InsightUpdate(status="DISMISSED", expected_version=1))
        dismissed = service.update(row.id, InsightUpdate(status="DISMISSED", expected_version=2))
        assert dismissed.dismissed_at == NOW
    processor.process(job(env, lot_id=lot.id))
    assert listed(env) == []
    assert listed(env, query=InsightQuery(status="DISMISSED"))[0].id == row.id


def test_api_reads_and_user_controls_never_generate_and_are_owned(environment):
    env = environment
    with TestClient(app_for(env)) as client:
        assert client.get("/api/v1/insights", headers=ALICE).json()["data"] == []
    spending_fixture(env)
    InsightProcessor(env.factory, clock=lambda: NOW).process(job(env))
    row = listed(env)[0]
    url = f"/api/v1/insights/{row.id}"
    with TestClient(app_for(env)) as client:
        response = client.get(url, headers=ALICE)
        assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
        assert (
            "user_id" not in response.json()["data"]
            and "deduplication_key" not in response.json()["data"]
        )
        assert client.get(url, headers=BOB).status_code == 404
        assert (
            client.patch(
                url, headers=BOB, json={"status": "DISMISSED", "expected_version": 1}
            ).status_code
            == 404
        )
        assert client.get("/api/v1/insights", headers=BOB).json()["data"] == []
        assert (
            client.patch(
                url, headers=ALICE, json={"status": "READ", "expected_version": 1}
            ).status_code
            == 200
        )
        assert client.get("/api/v1/insights?user_id=x", headers=ALICE).status_code == 422
        assert client.get("/api/v1/insights?status=FAKE", headers=ALICE).status_code == 422
        assert (
            client.patch(
                url, headers=ALICE, json={"status": "ACTIVE", "expected_version": 2}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/insights", headers=ALICE, json={"type": "SPENDING_CHANGE"}
            ).status_code
            == 405
        )
        assert (
            len(client.get("/api/v1/insights?limit=1&offset=1", headers=ALICE).json()["data"]) == 1
        )


def test_worker_rollback_retries_and_operator_requeue_preserve_other_subscriber(
    environment, monkeypatch, caplog
):
    env = environment
    spending_fixture(env)
    state = SimpleNamespace(now=NOW)
    task = job(env)
    processor = InsightProcessor(env.factory, clock=lambda: state.now)
    original = InsightService.record

    def fail_after_record(self, *args):
        original(self, *args)
        raise OperationalError("private SQL", {}, Exception("private credentials"))

    monkeypatch.setattr(InsightService, "record", fail_after_record)
    for attempt, delay in [(1, 5), (2, 10), (3, 0)]:
        processor.process(task)
        with env.factory() as session:
            event = session.get(OutboxEvent, task.event_id)
            assert event.insight_attempt_count == attempt
            assert event.insight_processed_at is None
            assert event.failure_code is None and event.attempt_count == 0
            assert event.insight_failure_code == "insight_persistence_failed"
            assert bool(event.insight_failed_at) is (attempt == 3)
            assert session.scalar(select(func.count()).select_from(Insight)) == 0
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(OutboxEvent)
                    .where(OutboxEvent.event_type == "INSIGHT_CREATED")
                )
                == 0
            )
        processor.process(task)  # Backoff/exhaustion prevent another attempt.
        state.now += timedelta(seconds=delay)
    assert "private SQL" not in caplog.text and "private credentials" not in caplog.text
    monkeypatch.setattr(InsightService, "record", original)
    processor.retry(task.event_id)
    processor.process(task)
    assert len(listed(env)) == 2
    with pytest.raises(Conflict):
        processor.retry(task.event_id)


def test_permanent_failures_are_recorded_and_duplicate_deliveries_serialize(
    environment, monkeypatch
):
    env = environment
    task = job(env)
    original = InsightEvaluation.financial

    def invalid(self):
        raise ValueError("private invalid source")

    monkeypatch.setattr(InsightEvaluation, "financial", invalid)
    processor = InsightProcessor(env.factory, clock=lambda: NOW)
    processor.process(task)
    with env.factory() as session:
        row = session.get(OutboxEvent, task.event_id)
        assert row.insight_attempt_count == 1 and row.insight_failed_at == NOW
        assert row.insight_failure_code == "insight_validation_failed"
    monkeypatch.setattr(InsightEvaluation, "financial", original)
    spending_fixture(env)
    task = job(env)
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(processor.process, [task, task]))
    assert len(listed(env)) == 2
    with env.factory() as session:
        assert session.get(OutboxEvent, task.event_id).insight_attempt_count == 1
    with pytest.raises(NotFound):
        processor.process(InsightTask(uuid4()))


def test_daily_scheduler_is_durable_concurrent_and_revisits_lots(environment):
    env = environment
    lot = stock(env)
    state = SimpleNamespace(now=NOW)
    processor = InsightProcessor(env.factory, clock=lambda: state.now)
    dispatcher = InsightDispatcher(
        env.factory, LocalInsightTaskQueue(processor), clock=lambda: state.now
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        counts = list(executor.map(lambda _: dispatcher.schedule_once(), range(2)))
    assert sum(counts) == 2  # Alice and Bob, only once each.
    assert dispatcher.schedule_once() == 0
    with env.factory() as session:
        rows = session.scalars(
            select(OutboxEvent).where(OutboxEvent.event_type == "INSIGHT_EVALUATION_REQUESTED")
        ).all()
        assert len(rows) == 3
        assert sum(row.evaluation_lot_id == lot.id for row in rows) == 1
    assert dispatcher.dispatch_once() == 5  # Purchase, inventory change, and scheduled tasks.
    assert dispatcher.dispatch_once() == 0
    assert len(listed(env)) == 1
    state.now += timedelta(days=1)
    assert dispatcher.schedule_once() == 2
    assert dispatcher.dispatch_once() == 3
    assert len(listed(env, now=state.now)) == 1
    assert listed(env, now=state.now)[0].id == listed(env)[0].id


def test_scheduling_and_dispatch_batches_are_bounded(environment):
    env = environment
    with env.factory() as session:
        for number in range(21):
            provision_user(session, VerifiedIdentity(f"schedule-{number}"))
    dispatcher = InsightDispatcher(
        env.factory,
        LocalInsightTaskQueue(InsightProcessor(env.factory, clock=lambda: NOW)),
        clock=lambda: NOW,
    )
    assert dispatcher.schedule_once() == 20
    assert dispatcher.schedule_once() == 3
    assert dispatcher.schedule_once() == 0
    assert dispatcher.dispatch_once() == 20
    assert dispatcher.dispatch_once() == 3
    assert dispatcher.dispatch_once() == 0


def test_insight_and_scheduled_lot_foreign_keys_reject_cross_owner_links(environment):
    env = environment
    lot = stock(env)
    InsightProcessor(env.factory, clock=lambda: NOW).process(job(env, lot_id=lot.id))
    insight = listed(env)[0]
    with env.factory() as session, pytest.raises(IntegrityError), session.begin():
        session.add(
            OutboxEvent(
                user_id=env.bob.id, insight_id=insight.id, event_type="INSIGHT_CREATED", payload={}
            )
        )
        session.flush()
    with pytest.raises(IntegrityError):
        job(env, owner=env.bob, lot_id=lot.id)


def test_assistant_reads_insight_evidence_and_preserves_grounded_values(environment):
    env = environment
    spending_fixture(env)
    InsightProcessor(env.factory, clock=lambda: NOW).process(job(env))
    row = next(row for row in listed(env) if row.type == "SPENDING_CHANGE")
    model = ScriptedModel(
        calls(call("get_insight", {"insight_id": str(row.id)})),
        final(
            "Recorded spending: {{value}}.",
            sources=["call_summary"],
            refs=[reference("/data/source_data/metrics/current_total")],
        ),
    )
    with TestClient(app_for(env, model)) as client:
        conversation = client.post(
            "/api/v1/assistant/conversations", headers=ALICE, json={}
        ).json()["data"]["id"]
        response = client.post(
            f"/api/v1/assistant/conversations/{conversation}/messages",
            headers=ALICE,
            json={"content": "Explain my spending insight", "idempotency_key": str(uuid4())},
        )
        assert response.status_code == 201, response.text
        assert (
            response.json()["data"]["assistant_message"]["content"]
            == "Recorded spending: 450.000000."
        )
        assert model.requests[1].feedback[0].result.data["calculation"]["version"] == "insights.v1"


def test_new_assistant_read_tools_preserve_ownership_and_validate_arguments(environment):
    env = environment
    lot = stock(env)
    InsightProcessor(env.factory, clock=lambda: NOW).process(job(env, lot_id=lot.id))
    row = listed(env)[0]
    registry = ToolRegistry()
    with env.factory() as session:
        alice = ToolContext(session, env.alice, NOW)
        bob = ToolContext(session, env.bob, NOW)
        own = registry.invoke(alice, call("get_insights")).result
        assert own.status == "SUCCEEDED" and own.data["items"][0]["id"] == str(row.id)
        assert registry.invoke(bob, call("get_insights")).result.data["items"] == []
        foreign = registry.invoke(bob, call("get_insight", {"insight_id": str(row.id)})).result
        assert foreign.status == "FAILED" and foreign.error.code == "not_found"
        for arguments in [
            {"query": " "},
            {"query": "diet", "user_id": str(env.bob.id)},
            {"query": "diet", "sql": "SELECT *"},
        ]:
            rejected = registry.invoke(alice, call("get_memories", arguments)).result
            assert rejected.error.code == "invalid_arguments"
