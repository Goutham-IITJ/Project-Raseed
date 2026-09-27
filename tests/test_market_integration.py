from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from m7_fixtures import NOW, purchase
from market_fixtures import FakeMarket, offer, product_line, read, search, worker
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.app.market.models import MarketPriceObservation, MarketSearch
from backend.app.market.provider import MarketFailure
from backend.app.market.schemas import ProviderResult, SearchCreate
from backend.app.market.service import MarketService
from backend.app.market.worker import MarketTask
from backend.app.purchases.errors import Conflict, NotFound
from backend.app.purchases.models import OutboxEvent, Product, Purchase

pytestmark = pytest.mark.integration


def test_durable_lookup_preserves_purchase_and_external_provenance(environment):
    env = environment
    product, purchased, line = product_line(env)
    row = search(env, line)
    assert row.status == "PENDING" and row.observations == []
    processor, dispatcher, fake = worker(env)
    assert dispatcher.dispatch_once() == 1
    result = read(env, row.id)
    observation = result.observations[0]
    assert result.status == "SUCCEEDED"
    assert observation.product_id == product.id and observation.provenance == "EXTERNAL"
    assert observation.offer.source == "Fixture merchant feed"
    assert observation.offer.observed_at == NOW and observation.fetched_at == NOW
    assert observation.expires_at == NOW + timedelta(minutes=15)
    assert observation.offer.shipping is None and observation.offer.tax is None
    assert observation.comparison.conclusion == "LOWER_DISPLAY_PRICE"
    assert observation.comparison.matching.rule == "market.v1:exact_gtin"
    assert result.target.unit_price == Decimal("100")
    assert set(fake.calls[0].model_dump()) == {"identity", "country", "postal_code", "currency"}
    with env.factory() as session:
        assert session.get(Purchase, purchased.id).grand_total == Decimal("100")
        purchase_event = session.scalars(
            select(OutboxEvent).where(OutboxEvent.event_type == "PURCHASE_CREATED")
        ).one()
        assert purchase_event.published_at is None and purchase_event.wallet_processed_at is None
        assert purchase_event.insight_processed_at is None
        event = session.scalars(
            select(OutboxEvent).where(OutboxEvent.market_search_id == row.id)
        ).one()
        assert event.published_at == NOW
    processor.process(MarketTask(row.id))
    assert dispatcher.dispatch_once() == 0 and len(fake.calls) == 1


def test_uncertain_identity_is_preserved_without_canonical_association_or_conclusion(environment):
    env = environment
    product, _, line = product_line(
        env, metadata={"identity_source": "INFERRED", "gtin": "4006381333931"}
    )
    row = search(env, line)
    worker(env)[1].dispatch_once()
    observation = read(env, row.id).observations[0]
    assert observation.product_id is None
    assert observation.comparison.matching.status == "UNCERTAIN"
    assert observation.comparison.matching.confidence == Decimal("0.5")
    assert observation.comparison.conclusion == "NOT_COMPARABLE"


def test_invalid_optional_catalog_metadata_stays_unknown_without_breaking_lookup(environment):
    env = environment
    product, _, line = product_line(
        env,
        metadata={
            "identity_source": "OBSERVED",
            "gtin": "invalid",
            "mpn": {"untrusted": "value"},
            "variant": " ",
            "pack": {"quantity": "500", "unit": "g"},
        },
    )
    with env.factory.begin() as session:
        session.get(Product, product.id).brand = ""
    row = search(env, line)
    worker(env)[1].dispatch_once()
    result = read(env, row.id)
    assert result.status == "SUCCEEDED"
    assert result.target.identity.model_dump(exclude_none=True) == {"name": "Acme coffee"}
    assert result.observations[0].comparison.matching.status == "UNCERTAIN"
    assert result.observations[0].comparison.conclusion == "NOT_COMPARABLE"


def test_unassociated_line_and_product_only_queries_do_not_invent_baselines(environment):
    env = environment
    unknown = purchase(env, line_items=[{"raw_name": "Coffee"}]).line_items[0]
    row = search(env, unknown)
    worker(env)[1].dispatch_once()
    result = read(env, row.id)
    assert result.target.identity.gtin is None and result.target.unit_price is None
    assert not result.observations[0].comparison.comparable
    product, _, _ = product_line(env)
    with env.factory() as session:
        product_search = MarketService(session, env.alice, clock=lambda: NOW).search(
            SearchCreate(product_id=product.id, country="US")
        )
    worker(env)[1].dispatch_once()
    result = read(env, product_search.id)
    assert result.target.unit_price is None and result.target.currency == "INR"
    assert "no_historical_unit_price" in result.observations[0].comparison.reasons


def test_concurrent_searches_reuse_one_owned_job_and_fresh_cache(environment):
    env = environment
    _, _, line = product_line(env)
    barrier = Barrier(4)

    def submit(_):
        barrier.wait(timeout=10)
        return search(env, line).id

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(submit, range(4)))
    assert len(set(ids)) == 1
    _, dispatcher, fake = worker(env)
    dispatcher.dispatch_once()
    assert search(env, line).id == ids[0]
    assert len(fake.calls) == 1
    assert search(env, line, postal_code="10001").id != ids[0]
    with env.factory() as session:
        assert session.scalar(select(func.count()).select_from(MarketSearch)) == 2


def test_expired_cache_stale_provider_time_and_earlier_expiry(environment):
    env = environment
    _, _, line = product_line(env)
    row = search(env, line)
    worker(env, FakeMarket(ProviderResult(offers=[offer(expires_at=NOW + timedelta(minutes=2))])))[
        1
    ].dispatch_once()
    stale = read(env, row.id, now=NOW + timedelta(minutes=2))
    assert stale.observations[0].stale and not stale.observations[0].comparison.comparable
    fresh = search(env, line, now=NOW + timedelta(minutes=2))
    assert fresh.id != row.id
    worker(env, clock=lambda: NOW + timedelta(minutes=20))[1].dispatch_once()
    result = read(env, fresh.id, now=NOW + timedelta(minutes=20))
    assert result.observations[0].offer.observed_at == NOW
    assert result.observations[0].fetched_at == NOW + timedelta(minutes=20)
    assert result.observations[0].stale  # Fetching old evidence never refreshes its timestamp.
    assert result.observations[0].comparison.conclusion == "NOT_COMPARABLE"


def test_empty_results_are_cached_without_fake_observations(environment):
    env = environment
    _, _, line = product_line(env)
    row = search(env, line)
    worker(env, FakeMarket(ProviderResult(offers=[])))[1].dispatch_once()
    result = read(env, row.id)
    assert result.status == "SUCCEEDED" and result.observations == []
    assert search(env, line).id == row.id
    assert search(env, line, now=NOW + timedelta(minutes=15)).id != row.id


def test_transient_retries_exhaustion_manual_recovery_and_safe_errors(environment):
    env = environment
    _, _, line = product_line(env)
    row = search(env, line)
    current = [NOW]
    fake = FakeMarket(*(MarketFailure("market_unavailable", retryable=True) for _ in range(3)))
    processor, dispatcher, _ = worker(env, fake, clock=lambda: current[0])
    for delay in (5, 10):
        assert dispatcher.dispatch_once() == 1
        result = read(env, row.id)
        assert result.status == "RETRY" and result.failure_code == "market_unavailable"
        assert result.next_attempt_at == current[0] + timedelta(seconds=delay)
        assert dispatcher.dispatch_once() == 0
        current[0] = result.next_attempt_at
    dispatcher.dispatch_once()
    assert read(env, row.id).status == "FAILED"
    assert dispatcher.dispatch_once() == 0
    with env.factory() as session:
        MarketService(session, env.alice, clock=lambda: current[0]).retry(row.id)
    dispatcher.dispatch_once()
    assert read(env, row.id).status == "SUCCEEDED" and len(fake.calls) == 4
    with env.factory() as session, pytest.raises(Conflict):
        MarketService(session, env.alice).retry(row.id)


@pytest.mark.parametrize(
    "code",
    ["market_configuration", "market_authorization", "market_invalid_data", "market_rejected"],
)
def test_permanent_failure_is_cached_without_automatic_retry(environment, code):
    env = environment
    _, _, line = product_line(env)
    row = search(env, line)
    _, dispatcher, fake = worker(env, FakeMarket(MarketFailure(code)))
    dispatcher.dispatch_once()
    assert read(env, row.id).status == "FAILED" and read(env, row.id).attempt_count == 1
    assert search(env, line).id == row.id
    assert dispatcher.dispatch_once() == 0 and len(fake.calls) == 1


def test_rate_limit_backoff_is_durable(environment):
    env = environment
    _, _, line = product_line(env)
    row = search(env, line)
    worker(env, FakeMarket(MarketFailure("market_rate_limited", retryable=True, retry_after=120)))[
        1
    ].dispatch_once()
    assert read(env, row.id).next_attempt_at == NOW + timedelta(seconds=120)


def test_network_has_no_database_locks_and_concurrent_worker_claim_is_fenced(environment):
    env = environment
    _, _, line = product_line(env)
    row = search(env, line)
    current = [NOW]
    processor, dispatcher, fake = worker(env, clock=lambda: current[0])

    def unlocked():
        with env.factory.begin() as session:
            session.execute(text("SET LOCAL lock_timeout = '500ms'"))
            assert (
                session.scalar(
                    select(MarketSearch).where(MarketSearch.id == row.id).with_for_update()
                ).status
                == "PROCESSING"
            )

    fake.before_search = unlocked
    dispatcher.dispatch_once()
    newer = search(env, line, now=NOW + timedelta(minutes=16))
    current[0] += timedelta(minutes=16)
    task = MarketTask(newer.id)
    first = processor.claim(task)
    assert processor.claim(task) is None
    current[0] += timedelta(minutes=5)
    second = processor.claim(task)
    assert second.token != first.token
    assert not processor.finish(first, ProviderResult(offers=[]))
    assert processor.finish(second, ProviderResult(offers=[]))


def test_crash_after_lookup_or_during_commit_recovers_without_partial_observations(
    environment, monkeypatch
):
    env = environment
    _, _, line = product_line(env)
    row = search(env, line)
    current = [NOW]
    processor, _, fake = worker(env, clock=lambda: current[0])
    original = processor._ack

    def fail(*args):
        raise SQLAlchemyError("simulated database failure")

    monkeypatch.setattr(processor, "_ack", fail)
    with pytest.raises(SQLAlchemyError):
        processor.process(MarketTask(row.id))
    assert read(env, row.id).status == "PROCESSING" and read(env, row.id).observations == []
    current[0] += timedelta(minutes=5)
    monkeypatch.setattr(processor, "_ack", original)
    processor.process(MarketTask(row.id))
    assert len(read(env, row.id).observations) == 1 and len(fake.calls) == 2


def test_repeated_crashes_exhaust_and_malformed_result_never_persists(environment):
    env = environment
    _, _, line = product_line(env)
    row = search(env, line)
    current = [NOW]
    processor, _, _ = worker(env, clock=lambda: current[0])
    for _ in range(3):
        assert processor.claim(MarketTask(row.id)) is not None
        current[0] += timedelta(minutes=5)
    assert processor.claim(MarketTask(row.id)) is None
    assert read(env, row.id).failure_code == "market_lease_expired"
    with env.factory() as session:
        MarketService(session, env.alice, clock=lambda: current[0]).retry(row.id)
    invalid = offer().model_copy(update={"price": Decimal("-1")})
    worker(
        env,
        FakeMarket(ProviderResult(offers=[offer(offer_id="good"), invalid])),
        clock=lambda: current[0],
    )[1].dispatch_once()
    result = read(env, row.id)
    assert result.status == "FAILED" and result.failure_code == "market_invalid_data"
    assert result.observations == []


@pytest.mark.parametrize("malformed", [None, {}, []])
def test_malformed_provider_result_type_fails_durably(environment, malformed):
    env = environment
    _, _, line = product_line(env)
    row = search(env, line)
    worker(env, FakeMarket(malformed))[1].dispatch_once()
    result = read(env, row.id)
    assert result.status == "FAILED" and result.failure_code == "market_invalid_data"
    assert result.observations == []


def test_future_observation_is_rejected_and_failed_retry_cannot_conflict_with_new_job(environment):
    env = environment
    _, _, line = product_line(env)
    row = search(env, line)
    worker(env, FakeMarket(ProviderResult(offers=[offer(observed_at=NOW + timedelta(seconds=1))])))[
        1
    ].dispatch_once()
    assert read(env, row.id).failure_code == "market_invalid_data"
    newer = search(env, line, now=NOW + timedelta(minutes=16))
    assert newer.id != row.id
    with env.factory() as session, pytest.raises(Conflict):
        MarketService(session, env.alice).retry(row.id)


def test_owned_services_and_composite_database_links(environment):
    env = environment
    product, _, line = product_line(env)
    row = search(env, line)
    worker(env)[1].dispatch_once()
    observation = read(env, row.id).observations[0]
    with env.factory() as session:
        service = MarketService(session, env.bob)
        for operation in (
            lambda: service.search(SearchCreate(line_item_id=line.id, country="US")),
            lambda: service.search(SearchCreate(product_id=product.id, country="US")),
            lambda: service.get(row.id),
            lambda: service.retry(row.id),
            lambda: service.observation(observation.id),
        ):
            with pytest.raises(NotFound):
                operation()
    with pytest.raises(IntegrityError), env.factory.begin() as session:
        session.get(MarketPriceObservation, observation.id).user_id = env.bob.id
    with pytest.raises(IntegrityError), env.factory.begin() as session:
        session.get(MarketSearch, row.id).user_id = env.bob.id
    with pytest.raises(IntegrityError), env.factory.begin() as session:
        event = session.scalars(
            select(OutboxEvent).where(OutboxEvent.market_search_id == row.id)
        ).one()
        event.user_id = env.bob.id
    with pytest.raises(NotFound):
        worker(env)[0].process(MarketTask(uuid4()))


def test_search_and_outbox_creation_are_atomic(environment, monkeypatch):
    env = environment
    _, purchased, line = product_line(env)
    with env.factory() as session:
        original = session.add

        def fail_outbox(row):
            if isinstance(row, OutboxEvent):
                raise SQLAlchemyError("outbox failure")
            original(row)

        monkeypatch.setattr(session, "add", fail_outbox)
        with pytest.raises(SQLAlchemyError):
            MarketService(session, env.alice, clock=lambda: NOW).search(
                SearchCreate(line_item_id=line.id, country="US")
            )
    with env.factory() as session:
        assert session.scalar(select(func.count()).select_from(MarketSearch)) == 0
        assert session.get(Purchase, purchased.id) is not None


def test_bounded_dispatch_batches(environment):
    env = environment
    _, _, line = product_line(env)
    for index in range(21):
        search(env, line, postal_code=str(10000 + index))
    _, dispatcher, fake = worker(env)
    assert dispatcher.dispatch_once() == 20
    assert dispatcher.dispatch_once() == 1
    assert dispatcher.dispatch_once() == 0
    assert len(fake.calls) == 21


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "OTHER"},
        {"status": "SUCCEEDED"},
        {"status": "PROCESSING"},
        {"attempt_count": 4},
        {"country": "uS"},
        {"fingerprint": "bad"},
        {"target": []},
        {"line_item_id": None, "purchase_id": None, "product_id": None},
    ],
)
def test_search_database_constraints(environment, changes):
    env = environment
    _, _, line = product_line(env)
    row = search(env, line)
    with pytest.raises(IntegrityError), env.factory.begin() as session:
        record = session.get(MarketSearch, row.id)
        for key, value in changes.items():
            setattr(record, key, value)


@pytest.mark.parametrize(
    "changes",
    [
        {"price": -1},
        {"shipping": -1},
        {"provenance": "OBSERVED"},
        {"match_confidence": 2},
        {"match_status": "INVENTED"},
        {"source": ""},
        {"observed_at": NOW + timedelta(seconds=1)},
        {"expires_at": NOW},
    ],
)
def test_observation_database_constraints(environment, changes):
    env = environment
    _, _, line = product_line(env)
    row = search(env, line)
    worker(env)[1].dispatch_once()
    observation = read(env, row.id).observations[0]
    with pytest.raises(IntegrityError), env.factory.begin() as session:
        record = session.get(MarketPriceObservation, observation.id)
        for key, value in changes.items():
            setattr(record, key, value)
