from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from m7_fixtures import NOW, purchase
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from wallet_fixtures import FakeWallet, ensure, worker

from backend.app.purchases.errors import Conflict, NotFound
from backend.app.purchases.models import OutboxEvent, Purchase
from backend.app.wallet.models import WalletPass
from backend.app.wallet.provider import WalletFailure
from backend.app.wallet.schemas import WalletCreate, WalletQuery
from backend.app.wallet.service import WalletService
from backend.app.wallet.worker import WalletTask, WalletWorkerRepository

pytestmark = pytest.mark.integration


def view(env, pass_id):
    with env.factory() as session:
        return WalletService(session, env.alice, FakeWallet()).get(pass_id)


def test_purchase_event_synchronizes_without_touching_canonical_or_other_subscribers(environment):
    env = environment
    item = purchase(env, amount="123.456789", merchant_name_raw="Observed merchant")
    with env.factory.begin() as session:
        event = session.scalars(select(OutboxEvent)).one()
        event.published_at = NOW - timedelta(seconds=5)
        event.insight_processed_at = NOW - timedelta(seconds=4)
        event.attempt_count = 2
        event.insight_attempt_count = 1
        event.payload = {"purchase_id": str(uuid4()), "user_id": str(env.bob.id)}
    processor, dispatcher, fake = worker(env)
    assert dispatcher.dispatch_once() == 1
    assert dispatcher.dispatch_once() == 0
    with env.factory() as session:
        row = session.scalars(select(WalletPass)).one()
        assert row.user_id == env.alice.id and row.purchase_id == item.id
        assert row.status == "SYNCED" and row.attempt_count == 1
        assert row.synced_at == NOW and row.lease_token is None
        event = session.scalars(select(OutboxEvent)).one()
        assert event.wallet_processed_at == NOW
        assert event.published_at == NOW - timedelta(seconds=5)
        assert event.insight_processed_at == NOW - timedelta(seconds=4)
        assert (event.attempt_count, event.insight_attempt_count) == (2, 1)
        assert session.get(Purchase, item.id).grand_total == item.grand_total
    processor.process(WalletTask(row.id))
    assert len(fake.calls) == 1
    assert fake.calls[0].merchant == "Observed merchant"
    assert fake.calls[0].total == item.grand_total


def test_handoff_and_api_creation_are_idempotent_with_concurrent_requests(environment):
    env = environment
    item = purchase(env)
    barrier = Barrier(4)

    def concurrent_create(index):
        barrier.wait(timeout=10)
        if index == 0:
            with env.factory.begin() as session:
                WalletWorkerRepository(session).handoff(NOW)
            return None
        return ensure(env, item).id

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(concurrent_create, range(4)))
    assert len(set(ids[1:])) == 1
    assert ensure(env, item).id == ids[1]
    with env.factory() as session:
        assert session.scalar(select(func.count()).select_from(WalletPass)) == 1


def test_provider_io_holds_no_database_transaction_or_pass_lock(environment):
    env = environment
    item = purchase(env)
    row = ensure(env, item)
    processor, dispatcher, fake = worker(env)

    def unlocked():
        with env.factory.begin() as other:
            other.execute(text("SET LOCAL lock_timeout = '500ms'"))
            locked = other.scalar(
                select(WalletPass).where(WalletPass.id == row.id).with_for_update()
            )
            assert locked.status in {"SYNCING", "SYNCED"}

    fake.before_sync = unlocked
    assert dispatcher.dispatch_once() == 1
    with env.factory() as session:
        fake.before_link = lambda: (
            unlocked(),
            pytest.fail("open transaction") if session.in_transaction() else None,
        )
        link = WalletService(session, env.alice, fake).add_to_wallet(row.id)
    assert link.save_url.startswith("https://pay.google.com/")


def test_handoff_failure_rolls_back_pass_and_ack_but_never_purchase(environment, monkeypatch):
    from backend.app.wallet import worker as module

    env = environment
    item = purchase(env)
    original = module.ensure_pass

    def fail(*args):
        original(*args)
        raise SQLAlchemyError("test database failure")

    monkeypatch.setattr(module, "ensure_pass", fail)
    with pytest.raises(SQLAlchemyError), env.factory.begin() as session:
        WalletWorkerRepository(session).handoff(NOW)
    with env.factory() as session:
        assert session.scalar(select(func.count()).select_from(WalletPass)) == 0
        assert session.scalars(select(OutboxEvent)).one().wallet_processed_at is None
        assert session.get(Purchase, item.id) is not None
    monkeypatch.setattr(module, "ensure_pass", original)
    assert worker(env)[1].dispatch_once() == 1


def test_transient_failure_backoff_exhaustion_and_explicit_retry(environment):
    env = environment
    item = purchase(env)
    current = [NOW]
    fake = FakeWallet(*(WalletFailure("wallet_unavailable", retryable=True) for _ in range(3)))
    processor, dispatcher, _ = worker(env, fake, clock=lambda: current[0])
    row = ensure(env, item)
    assert dispatcher.dispatch_once() == 1
    first = view(env, row.id)
    assert first.status == "RETRY" and first.last_error_code == "wallet_unavailable"
    assert first.next_attempt_at == NOW + timedelta(seconds=5)
    with env.factory() as session:
        retry = WalletService(session, env.alice, fake).sync(row.id)
    assert retry.attempt_count == 1 and retry.next_attempt_at == first.next_attempt_at
    assert dispatcher.dispatch_once() == 0
    current[0] += timedelta(seconds=5)
    assert dispatcher.dispatch_once() == 1
    second = view(env, row.id)
    assert second.next_attempt_at == current[0] + timedelta(seconds=10)
    current[0] = second.next_attempt_at
    assert dispatcher.dispatch_once() == 1
    assert view(env, row.id).status == "FAILED"
    assert dispatcher.dispatch_once() == 0
    processor.retry(row.id)
    assert dispatcher.dispatch_once() == 1
    final = view(env, row.id)
    assert final.status == "SYNCED" and final.attempt_count == 1
    assert final.last_error_code is None and final.last_error_at is None
    assert len({entry.object_id for entry in fake.calls}) == 1
    with pytest.raises(Conflict):
        processor.retry(row.id)


def test_rate_limit_guidance_is_persisted(environment):
    env = environment
    row = ensure(env, purchase(env))
    fake = FakeWallet(WalletFailure("wallet_rate_limited", retryable=True, retry_after=120))
    assert worker(env, fake)[1].dispatch_once() == 1
    assert view(env, row.id).next_attempt_at == NOW + timedelta(seconds=120)


@pytest.mark.parametrize(
    "failure", ["wallet_configuration", "wallet_authorization", "wallet_rejected"]
)
def test_permanent_failure_never_retries_or_rolls_back_purchase(environment, failure):
    env = environment
    item = purchase(env)
    row = ensure(env, item)
    processor, dispatcher, fake = worker(env, FakeWallet(WalletFailure(failure)))
    assert dispatcher.dispatch_once() == 1
    assert view(env, row.id).status == "FAILED"
    assert view(env, row.id).attempt_count == 1
    assert dispatcher.dispatch_once() == 0
    with env.factory() as session:
        assert session.get(Purchase, item.id).grand_total == item.grand_total


def test_unconfigured_pass_recovers_and_issuer_change_does_not_reidentify(environment):
    env = environment
    row = ensure(env, purchase(env))
    processor, dispatcher, fake = worker(env)
    fake.configured = False
    assert dispatcher.dispatch_once() == 1
    first = view(env, row.id)
    assert first.status == "FAILED" and first.object_id is None
    assert first.last_error_code == "wallet_configuration" and fake.calls == []
    fake.configured = True
    processor.retry(row.id)
    dispatcher.dispatch_once()
    synced = view(env, row.id)
    fake.identifiers = lambda purchase_id: (
        "999.raseed_receipts_v1",
        f"999.raseed_purchase_{purchase_id.hex}",
    )
    with env.factory() as session:
        WalletService(session, env.alice, fake).sync(row.id)
    dispatcher.dispatch_once()
    failed = view(env, row.id)
    assert failed.status == "FAILED" and failed.object_id == synced.object_id
    assert len(fake.calls) == 1


def test_duplicate_workers_claim_once_and_stale_results_are_fenced(environment):
    env = environment
    row = ensure(env, purchase(env))
    current = [NOW]
    processor, _, fake = worker(env, clock=lambda: current[0])
    task = WalletTask(row.id)
    barrier = Barrier(2)

    def claim(_):
        barrier.wait(timeout=10)
        return processor.claim(task)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, range(2)))
    first = next(value for value in claims if value is not None)
    assert claims.count(None) == 1
    current[0] += timedelta(seconds=300)
    assert not processor.finish(first)
    second = processor.claim(task)
    assert second.token != first.token
    assert not processor.finish(first, WalletFailure("wallet_authorization"))
    assert processor.finish(second)
    assert view(env, row.id).status == "SYNCED"


def test_repeated_worker_crashes_exhaust_and_can_be_requeued(environment):
    env = environment
    row = ensure(env, purchase(env))
    current = [NOW]
    processor, dispatcher, _ = worker(env, clock=lambda: current[0])
    for _ in range(3):
        assert processor.claim(WalletTask(row.id)) is not None
        current[0] += timedelta(seconds=300)
    assert dispatcher.dispatch_once() == 1
    failed = view(env, row.id)
    assert failed.status == "FAILED" and failed.last_error_code == "wallet_lease_expired"
    processor.retry(row.id)
    assert dispatcher.dispatch_once() == 1
    assert view(env, row.id).status == "SYNCED"


def test_crash_after_external_success_converges_on_one_object(environment, monkeypatch):
    env = environment
    row = ensure(env, purchase(env))
    current = [NOW]
    processor, _, fake = worker(env, clock=lambda: current[0])
    original = processor.finish

    def fail(*args):
        raise SQLAlchemyError("crash after Google success")

    monkeypatch.setattr(processor, "finish", fail)
    with pytest.raises(SQLAlchemyError):
        processor.process(WalletTask(row.id))
    assert len(fake.objects) == 1 and view(env, row.id).status == "SYNCING"
    current[0] += timedelta(seconds=300)
    monkeypatch.setattr(processor, "finish", original)
    processor.process(WalletTask(row.id))
    assert len(fake.calls) == 2 and len(fake.objects) == 1
    assert view(env, row.id).status == "SYNCED"


def test_bound_batches_and_independent_owner_projections(environment):
    env = environment
    for _ in range(21):
        purchase(env)
    purchase(env, owner=env.bob)
    _, dispatcher, fake = worker(env)
    assert dispatcher.dispatch_once() == 20
    assert dispatcher.dispatch_once() == 2
    assert dispatcher.dispatch_once() == 0
    assert len(fake.objects) == 22
    with env.factory() as session:
        service = WalletService(session, env.alice, fake)
        assert len(service.list(WalletQuery(limit=100))) == 21
        assert len(service.list(WalletQuery(limit=10, offset=20))) == 1
        assert service.list(WalletQuery(status="FAILED")) == []


def test_service_and_database_enforce_owned_purchase_links(environment):
    env = environment
    item = purchase(env)
    row = ensure(env, item)
    with env.factory() as session:
        service = WalletService(session, env.bob, FakeWallet())
        for operation in (
            lambda: service.create(WalletCreate(purchase_id=item.id)),
            lambda: service.get(row.id),
            lambda: service.sync(row.id),
            lambda: service.add_to_wallet(row.id),
        ):
            with pytest.raises(NotFound):
                operation()
        assert service.list(WalletQuery(purchase_id=item.id)) == []
    with pytest.raises(IntegrityError), env.factory.begin() as session:
        session.get(WalletPass, row.id).user_id = env.bob.id
    with pytest.raises(NotFound):
        worker(env)[0].process(WalletTask(uuid4()))


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "OTHER"},
        {"provider": "OTHER"},
        {"pass_type": "TICKET"},
        {"attempt_count": 4},
        {"status": "SYNCING"},
        {"status": "SYNCED"},
        {"status": "FAILED"},
        {"object_id": "123.bad"},
        {"class_id": "bad/path"},
        {"lease_token": uuid4()},
        {"last_error_code": "wallet_timeout"},
    ],
)
def test_wallet_lifecycle_constraints(environment, changes):
    env = environment
    row = ensure(env, purchase(env))
    with pytest.raises(IntegrityError), env.factory.begin() as session:
        stored = session.get(WalletPass, row.id)
        for key, value in changes.items():
            setattr(stored, key, value)
