import socket
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from threading import Thread
from types import SimpleNamespace
from typing import Annotated
from uuid import UUID, uuid4

import httpx
import pytest
import uvicorn
from fastapi import Depends
from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.orm import Session

from backend.app.analytics.repository import AnalyticsRepository
from backend.app.analytics.schemas import AnalyticsQuery, ComparisonQuery
from backend.app.analytics.service import AnalyticsService
from backend.app.api.analytics import get_analytics_service
from backend.app.api.dependencies import get_current_user, get_session
from backend.app.api.purchases import get_purchase_service
from backend.app.database import make_session_factory
from backend.app.identity.context import CurrentUser
from backend.app.identity.schemas import PreferencePatch
from backend.app.identity.service import UserService
from backend.app.purchases.models import OutboxEvent, Payment
from backend.app.purchases.schemas import (
    CategoryCreate,
    ExtractionRunCreate,
    MerchantCreate,
    ProductCreate,
    PurchaseCreate,
    ReceiptCreate,
)
from backend.app.purchases.service import PurchaseService

pytestmark = pytest.mark.integration
ALICE = {"Authorization": "Bearer alice-token"}
BOB = {"Authorization": "Bearer bob-token"}
DATES = {"start_date": "2026-09-01", "end_date": "2026-10-01"}
NOW = datetime(2026, 9, 26, 6, tzinfo=timezone.utc)
START = datetime(2026, 8, 31, 18, 30, tzinfo=timezone.utc)
END = datetime(2026, 9, 30, 18, 30, tzinfo=timezone.utc)
ANALYTICS_PATHS = [
    "spending-summary",
    "spending-by-category",
    "spending-by-merchant",
    "period-comparison",
]


@pytest.fixture
def analytics(database, client):
    factory = make_session_factory(database)
    env = SimpleNamespace(factory=factory, client=client, database=database)
    for name, headers in (("alice", ALICE), ("bob", BOB)):
        profile = client.get("/api/v1/me", headers=headers).json()["data"]
        setattr(env, name, CurrentUser(UUID(profile["id"]), profile["firebase_uid"]))

    def frozen_analytics(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
        session: Annotated[Session, Depends(get_session)],
    ):
        return AnalyticsService(session, current_user, clock=lambda: NOW)

    def frozen_purchases(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
        session: Annotated[Session, Depends(get_session)],
    ):
        return PurchaseService(session, current_user, clock=lambda: NOW)

    client.app.dependency_overrides[get_analytics_service] = frozen_analytics
    client.app.dependency_overrides[get_purchase_service] = frozen_purchases
    yield env
    client.app.dependency_overrides.clear()


def purchase(env, *, owner=None, **changes):
    with env.factory() as session:
        return PurchaseService(session, owner or env.alice).create_purchase(
            PurchaseCreate.model_validate(
                {
                    "merchant_name_raw": "Fixture store",
                    "purchase_type": "RETAIL",
                    "purchased_at": datetime(2026, 9, 15, 12, tzinfo=timezone.utc),
                    "currency": "INR",
                    "grand_total": "1.000001",
                    "payment_status": "UNKNOWN",
                    **changes,
                }
            )
        )


def result(env, endpoint, *, headers=ALICE, **filters):
    response = env.client.get(
        f"/api/v1/analytics/{endpoint}", headers=headers, params={**DATES, **filters}
    )
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()["data"]


@pytest.fixture
def populated(analytics):
    env = analytics
    with env.factory() as session:
        service = PurchaseService(session, env.alice)
        env.parent = service.create_category(CategoryCreate(name="Shopping", slug="shopping"))
        env.grocery = service.create_category(
            CategoryCreate(name="Groceries", slug="groceries", parent_id=env.parent.id)
        )
        env.household = service.create_category(CategoryCreate(name="Household", slug="household"))
        env.product = service.create_product(
            ProductCreate(canonical_name="Fixture product", category_id=env.grocery.id)
        )
        env.store = service.create_merchant(
            MerchantCreate(canonical_name="Same Store", address="First address")
        )
        env.other_store = service.create_merchant(
            MerchantCreate(canonical_name="Same Store", address="Second address")
        )
        env.private_store = service.create_merchant(MerchantCreate(canonical_name="Bob only store"))
        env.private_category = service.create_category(
            CategoryCreate(name="Bob only category", slug="bob-only")
        )
    env.first = purchase(
        env,
        purchased_at=START,
        grand_total="10.30",
        merchant_id=env.store.id,
        merchant_name_raw="SAME STORE #1",
        category_id=env.parent.id,
        payment_status="PAID",
        line_items=[
            {"raw_name": "Food", "category_id": env.grocery.id, "line_total": "7.000001"},
            {"raw_name": "Supplies", "category_id": env.household.id, "line_total": "2.999999"},
            {
                "raw_name": "Unknown amount/category",
                "product_id": env.product.id,
                "quantity": "2",
                "unit_price": "25",
            },
        ],
        payments=[
            {"method": "CARD", "currency": "INR", "amount": "5.10"},
            {"method": "CASH", "currency": "INR", "amount": "5.20"},
        ],
    )
    env.second = purchase(
        env,
        grand_total="0.20",
        merchant_id=env.store.id,
        merchant_name_raw="Same Store",
        category_id=env.grocery.id,
        payment_status="PAID",
        line_items=[
            {"raw_name": "Food A", "category_id": env.grocery.id, "line_total": "0.10"},
            {"raw_name": "Food B", "category_id": env.grocery.id, "line_total": "0.10"},
        ],
    )
    env.third = purchase(
        env,
        purchased_at=END - timedelta(microseconds=1),
        grand_total="3.00",
        merchant_id=env.other_store.id,
        payment_status="PARTIALLY_PAID",
        line_items=[{"raw_name": "Unpriced supplies", "category_id": env.household.id}],
        payments=[{"method": "CASH", "currency": "INR", "amount": "1"}],
    )
    env.fourth = purchase(env, grand_total="0.10", purchase_type="SERVICE", payment_status="UNPAID")
    env.usd = purchase(
        env,
        currency="USD",
        grand_total="4",
        merchant_id=env.store.id,
        category_id=env.parent.id,
        line_items=[
            {
                "raw_name": "Different line basis",
                "category_id": env.grocery.id,
                "line_total": "4.50",
            }
        ],
    )
    env.before = purchase(env, purchased_at=START - timedelta(microseconds=1), grand_total="1000")
    env.after = purchase(env, purchased_at=END, grand_total="2000")
    env.bob_shared = purchase(
        env,
        owner=env.bob,
        grand_total="9999",
        merchant_id=env.store.id,
        category_id=env.parent.id,
        payment_status="PAID",
        line_items=[
            {
                "raw_name": "Private item",
                "category_id": env.grocery.id,
                "product_id": env.product.id,
                "line_total": "9999",
            }
        ],
        payments=[{"method": "CASH", "currency": "INR", "amount": "9999"}],
    )
    env.bob_private = purchase(
        env,
        owner=env.bob,
        grand_total="9000",
        currency="EUR",
        merchant_id=env.private_store.id,
        category_id=env.private_category.id,
    )
    # Payment.created_at is ingestion metadata, not the spending period.
    with env.factory.begin() as session:
        session.execute(
            update(Payment).values(created_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
        )
    return env


def test_summary_is_exact_owned_and_not_multiplied_by_children(populated):
    env = populated
    data = result(env, "spending-summary")
    assert data == result(env, "spending-summary")
    assert data["provenance"] == "DERIVED"
    assert data["period"] == {
        **DATES,
        "timezone": "Asia/Kolkata",
        "start_at": "2026-08-31T18:30:00Z",
        "end_at": "2026-09-30T18:30:00Z",
    }
    assert [row["currency"] for row in data["currencies"]] == ["INR", "USD"]
    inr, usd = data["currencies"]
    assert inr["purchase_count"] == 4
    assert Decimal(inr["total_spent"]) == Decimal("13.60")
    assert Decimal(inr["average_purchase"]) == Decimal("3.40")
    assert Decimal(inr["smallest_purchase"]) == Decimal("0.10")
    assert Decimal(inr["largest_purchase"]) == Decimal("10.30")
    assert inr["first_purchased_at"] == "2026-08-31T18:30:00Z"
    assert inr["last_purchased_at"] == "2026-09-30T18:29:59.999999Z"
    assert Decimal(inr["recorded_payment_total"]) == Decimal("11.30")
    assert inr["payment_count"] == 3 and inr["purchases_with_recorded_payments"] == 2
    assert Decimal(usd["total_spent"]) == 4 and usd["purchase_count"] == 1
    assert usd["payment_count"] == 0 and Decimal(usd["recorded_payment_total"]) == 0
    assert "user_id" not in str(data) and "reference" not in str(data)
    with env.factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
            )
            == 9
        )


def test_currency_selection_empty_results_and_payment_coverage(populated):
    env = populated
    rows = result(env, "spending-summary", currency="USD")["currencies"]
    assert len(rows) == 1 and rows[0]["currency"] == "USD"
    empty = result(env, "spending-summary", currency="CHF")["currencies"][0]
    assert empty["currency"] == "CHF" and empty["purchase_count"] == 0
    assert Decimal(empty["total_spent"]) == 0
    for field in (
        "average_purchase",
        "smallest_purchase",
        "largest_purchase",
        "first_purchased_at",
        "last_purchased_at",
    ):
        assert empty[field] is None
    paid = result(env, "spending-summary", currency="INR", payment_status="PAID")["currencies"][0]
    assert paid["purchase_count"] == 2 and paid["purchases_with_recorded_payments"] == 1
    assert Decimal(paid["total_spent"]) == Decimal("10.50")
    assert Decimal(paid["recorded_payment_total"]) == Decimal("10.30")


def test_empty_owner_has_no_fabricated_currency_or_groups(analytics):
    for endpoint in ("spending-summary", "period-comparison"):
        assert result(analytics, endpoint)["currencies"] == []
    for endpoint in ("spending-by-category", "spending-by-merchant"):
        data = result(analytics, endpoint)
        assert data["groups"] == [] and data["has_more"] is False
    comparison = result(analytics, "period-comparison", currency="INR")["currencies"][0]
    assert Decimal(comparison["absolute_change"]) == 0
    assert comparison["percentage_change"] is None


def test_purchase_category_groups_reconcile_without_implicit_hierarchy_rollup(populated):
    env = populated
    data = result(env, "spending-by-category", currency="INR")
    assert data["basis"] == "purchase"
    groups = {row["category_id"]: row for row in data["groups"]}
    assert set(groups) == {str(env.parent.id), str(env.grocery.id), None}
    assert Decimal(groups[str(env.parent.id)]["total_amount"]) == Decimal("10.30")
    assert Decimal(groups[str(env.grocery.id)]["total_amount"]) == Decimal("0.20")
    assert groups[str(env.grocery.id)]["parent_id"] == str(env.parent.id)
    assert groups[None]["category_name"] is None
    assert Decimal(groups[None]["total_amount"]) == Decimal("3.10")
    assert sum(Decimal(row["total_amount"]) for row in groups.values()) == Decimal("13.60")
    assert sum(row["purchase_count"] for row in groups.values()) == 4
    assert all(
        row["line_item_count"] is None and row["unknown_amount_count"] == 0
        for row in groups.values()
    )
    assert Decimal(groups[str(env.parent.id)]["share_of_known_total_percent"]) == Decimal(
        "75.735294"
    )


def test_line_categories_preserve_unknowns_and_independent_amount_basis(populated):
    env = populated
    data = result(env, "spending-by-category", basis="line_item", currency="INR")
    groups = {row["category_id"]: row for row in data["groups"]}
    grocery = groups[str(env.grocery.id)]
    assert Decimal(grocery["total_amount"]) == Decimal("7.200001")
    assert grocery["purchase_count"] == 2 and grocery["line_item_count"] == 3
    assert grocery["known_amount_count"] == 3 and grocery["unknown_amount_count"] == 0
    household = groups[str(env.household.id)]
    assert Decimal(household["total_amount"]) == Decimal("2.999999")
    assert household["known_amount_count"] == household["unknown_amount_count"] == 1
    assert household["purchase_count"] == 2
    assert groups[None]["total_amount"] is None and groups[None]["unknown_amount_count"] == 1
    assert groups[None]["share_of_known_total_percent"] is None
    assert Decimal(grocery["share_of_known_total_percent"]) == Decimal("70.588245")
    # Product.category_id and quantity * unit_price do not fabricate line facts.
    assert groups[None]["known_amount_count"] == 0
    usd = result(env, "spending-by-category", basis="line_item", currency="USD")["groups"]
    assert len(usd) == 1 and Decimal(usd[0]["total_amount"]) == Decimal("4.50")


def test_merchant_identity_coverage_and_exact_group_metrics(populated):
    env = populated
    rows = result(env, "spending-by-merchant", currency="INR")["groups"]
    assert [row["merchant_id"] for row in rows] == [
        str(env.store.id),
        str(env.other_store.id),
        None,
    ]
    assert rows[0]["merchant_name"] == rows[1]["merchant_name"] == "Same Store"
    assert Decimal(rows[0]["total_spent"]) == Decimal("10.50")
    assert rows[0]["purchase_count"] == 2
    assert Decimal(rows[0]["average_purchase"]) == Decimal("5.25")
    assert Decimal(rows[1]["total_spent"]) == 3
    assert rows[2]["merchant_name"] is None and Decimal(rows[2]["total_spent"]) == Decimal("0.10")
    assert Decimal(rows[0]["share_of_total_percent"]) == Decimal("77.205882")
    assert rows[0]["first_purchased_at"] == "2026-08-31T18:30:00Z"


@pytest.mark.parametrize("endpoint", ANALYTICS_PATHS)
def test_every_analytics_read_hides_other_owner_and_catalog_existence(populated, endpoint):
    env = populated
    data = result(env, endpoint)
    assert "Bob only" not in str(data) and "EUR" not in str(data)
    for field, value in (
        ("merchant_id", env.private_store.id),
        ("category_id", env.private_category.id),
    ):
        hidden = result(env, endpoint, **{field: str(value)})
        absent = result(env, endpoint, **{field: str(uuid4())})
        key = "currencies" if "currencies" in hidden else "groups"
        assert hidden[key] == absent[key] == []
    bob = result(env, endpoint, headers=BOB)
    assert "USD" not in str(bob)


@pytest.mark.parametrize("endpoint", ANALYTICS_PATHS)
@pytest.mark.parametrize(
    "extra", [{"user_id": "other"}, {"sql": "SELECT * FROM purchases"}, {"start_date": "bad"}]
)
def test_analytics_api_rejects_unapproved_inputs(analytics, endpoint, extra):
    response = analytics.client.get(
        f"/api/v1/analytics/{endpoint}", headers=ALICE, params={**DATES, **extra}
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == "validation_error"
    assert "SELECT" not in response.text


@pytest.mark.parametrize(
    "field,value,names,totals",
    [
        ("currency", "INR", {"first", "second", "third", "fourth"}, {"INR": "13.60"}),
        ("merchant_id", "store", {"first", "second", "usd"}, {"INR": "10.50", "USD": "4"}),
        ("category_id", "parent", {"first", "usd"}, {"INR": "10.30", "USD": "4"}),
        (
            "line_item_category_id",
            "grocery",
            {"first", "second", "usd"},
            {"INR": "10.50", "USD": "4"},
        ),
        ("product_id", "product", {"first"}, {"INR": "10.30"}),
        ("payment_status", "PAID", {"first", "second"}, {"INR": "10.50"}),
        ("purchase_type", "SERVICE", {"fourth"}, {"INR": "0.10"}),
    ],
)
def test_history_and_analytics_share_owned_filters(populated, field, value, names, totals):
    env = populated
    if field.endswith("_id"):
        value = str(getattr(env, value).id)
    filters = {field: value}
    response = env.client.get("/api/v1/purchases", headers=ALICE, params={**DATES, **filters})
    assert response.status_code == 200
    rows = response.json()["data"]
    assert {row["id"] for row in rows} == {str(getattr(env, name).id) for name in names}
    assert len(rows) == len(names)
    summary = result(env, "spending-summary", **filters)
    assert summary["filters"][field] == value
    assert {row["currency"]: Decimal(row["total_spent"]) for row in summary["currencies"]} == {
        currency: Decimal(amount) for currency, amount in totals.items()
    }
    if "first" in names:
        first = next(row for row in rows if row["id"] == str(env.first.id))
        assert len(first["line_items"]) == 3 and len(first["payments"]) == 2


def test_line_filters_match_one_line_and_restrict_line_contributions(populated):
    env = populated
    filters = {"product_id": str(env.product.id), "line_item_category_id": str(env.grocery.id)}
    assert (
        env.client.get("/api/v1/purchases", headers=ALICE, params={**DATES, **filters}).json()[
            "data"
        ]
        == []
    )
    for endpoint in ANALYTICS_PATHS:
        data = result(env, endpoint, **filters)
        assert data.get("currencies", data.get("groups")) == []
    groups = result(env, "spending-by-category", basis="line_item", product_id=str(env.product.id))[
        "groups"
    ]
    assert len(groups) == 1 and groups[0]["category_id"] is None
    assert groups[0]["line_item_count"] == 1 and groups[0]["total_amount"] is None
    groups = result(
        env, "spending-by-category", basis="line_item", line_item_category_id=str(env.grocery.id)
    )["groups"]
    assert {group["category_id"] for group in groups} == {str(env.grocery.id)}
    assert [group["currency"] for group in groups] == ["INR", "USD"]


def test_history_defaults_all_time_and_keeps_stable_pagination(populated):
    env = populated
    rows = env.client.get("/api/v1/purchases", headers=ALICE).json()["data"]
    assert len(rows) == 7
    assert rows[0]["id"] == str(env.after.id) and rows[-1]["id"] == str(env.before.id)
    assert [(row["purchased_at"], row["id"]) for row in rows] == sorted(
        [(row["purchased_at"], row["id"]) for row in rows], reverse=True
    )
    pages = [
        env.client.get(
            "/api/v1/purchases", headers=ALICE, params={"limit": 1, "offset": offset}
        ).json()["data"][0]
        for offset in range(len(rows))
    ]
    assert pages == rows
    named = env.client.get(
        "/api/v1/purchases", headers=ALICE, params={"period": "this_month"}
    ).json()["data"]
    assert len(named) == 5 and str(env.after.id) not in {row["id"] for row in named}
    foreign = env.client.get(f"/api/v1/purchases/{env.bob_shared.id}", headers=ALICE)
    absent = env.client.get(f"/api/v1/purchases/{uuid4()}", headers=ALICE)
    assert foreign.status_code == absent.status_code == 404 and foreign.json() == absent.json()
    assert (
        env.client.get(
            "/api/v1/purchases", headers=ALICE, params={"user_id": str(env.bob.id)}
        ).status_code
        == 422
    )


def test_filter_text_is_a_bound_value_not_an_expression(populated):
    env = populated
    expression = "' OR 1=1 --"
    assert result(env, "spending-summary", purchase_type=expression)["currencies"] == []
    response = env.client.get(
        "/api/v1/purchases", headers=ALICE, params={"purchase_type": expression}
    )
    assert response.status_code == 200 and response.json()["data"] == []
    assert result(env, "spending-summary")["currencies"][0]["purchase_count"] == 4


@pytest.mark.parametrize("endpoint", ["spending-by-category", "spending-by-merchant"])
def test_group_pagination_preserves_full_currency_denominators(populated, endpoint):
    env = populated
    whole = result(env, endpoint, limit=100)["groups"]
    pages = []
    for offset in range(len(whole)):
        page = result(env, endpoint, limit=1, offset=offset)
        assert page["has_more"] == (offset < len(whole) - 1)
        assert page["limit"] == 1 and page["offset"] == offset
        pages.extend(page["groups"])
    assert pages == whole
    empty = result(env, endpoint, offset=len(whole))
    assert empty["groups"] == [] and not empty["has_more"]


def test_equal_amount_groups_use_uuid_tiebreakers(analytics):
    env = analytics
    category_ids, merchant_ids = [], []
    with env.factory() as session:
        service = PurchaseService(session, env.alice)
        for index in range(3):
            category_ids.append(
                service.create_category(
                    CategoryCreate(name=f"Category {index}", slug=f"category-{index}")
                ).id
            )
            merchant_ids.append(
                service.create_merchant(MerchantCreate(canonical_name=f"Merchant {index}")).id
            )
    for category_id, merchant_id in zip(category_ids, merchant_ids, strict=True):
        purchase(env, category_id=category_id, merchant_id=merchant_id)
    purchase(env)
    for endpoint, field, values in (
        ("spending-by-category", "category_id", category_ids),
        ("spending-by-merchant", "merchant_id", merchant_ids),
    ):
        rows = result(env, endpoint)["groups"]
        assert [row[field] for row in rows] == [*sorted(str(value) for value in values), None]


def test_period_comparison_currency_union_zero_baselines_and_signed_changes(analytics):
    env = analytics
    for currency, current, previous in (
        ("INR", "0.30", "0.20"),
        ("USD", "5", None),
        ("EUR", None, "7"),
        ("JPY", "0", "0"),
    ):
        if current is not None:
            purchase(env, currency=currency, grand_total=current)
        if previous is not None:
            purchase(
                env,
                currency=currency,
                grand_total=previous,
                purchased_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
            )
    purchase(env, owner=env.bob, currency="GBP", grand_total="1000")
    data = result(
        env,
        "period-comparison",
        comparison_start_date="2026-08-01",
        comparison_end_date="2026-09-01",
    )
    assert [row["currency"] for row in data["currencies"]] == ["EUR", "INR", "JPY", "USD"]
    rows = {row["currency"]: row for row in data["currencies"]}
    assert Decimal(rows["INR"]["absolute_change"]) == Decimal("0.10")
    assert Decimal(rows["INR"]["percentage_change"]) == 50
    assert rows["INR"]["current_purchase_count"] == rows["INR"]["comparison_purchase_count"] == 1
    assert Decimal(rows["EUR"]["current_total"]) == 0
    assert Decimal(rows["EUR"]["absolute_change"]) == -7
    assert Decimal(rows["EUR"]["percentage_change"]) == -100
    assert rows["EUR"]["purchase_count_change"] == -1
    assert rows["USD"]["percentage_change"] is None and rows["USD"]["purchase_count_change"] == 1
    assert rows["JPY"]["percentage_change"] is None and Decimal(rows["JPY"]["absolute_change"]) == 0


def test_named_and_custom_previous_periods_and_explicit_unequal_ranges(analytics):
    env = analytics
    purchase(env, purchased_at=datetime(2026, 8, 1, 12, tzinfo=timezone.utc), grand_total="10")
    purchase(env, purchased_at=datetime(2026, 8, 2, 12, tzinfo=timezone.utc), grand_total="20")
    purchase(env, grand_total="45")
    default = env.client.get("/api/v1/analytics/period-comparison", headers=ALICE).json()["data"]
    assert default["period"]["start_date"] == "2026-09-01"
    assert default["comparison_period"]["start_date"] == "2026-08-01"
    assert Decimal(default["currencies"][0]["comparison_total"]) == 30
    assert Decimal(default["currencies"][0]["percentage_change"]) == 50
    custom = result(env, "period-comparison")
    assert custom["comparison_period"]["start_date"] == "2026-08-02"
    assert Decimal(custom["currencies"][0]["comparison_total"]) == 20
    unequal = result(
        env,
        "period-comparison",
        start_date="2026-09-15",
        end_date="2026-09-16",
        comparison_start_date="2026-08-01",
        comparison_end_date="2026-09-01",
    )
    assert Decimal(unequal["currencies"][0]["percentage_change"]) == 50


def test_large_aggregate_amounts_retain_micro_units(analytics):
    env = analytics
    for _ in range(3):
        purchase(env, grand_total="99999999999999.999999")
    purchase(env, purchased_at=datetime(2026, 8, 15, tzinfo=timezone.utc), grand_total="0.000001")
    with env.factory() as session, localcontext() as context:
        context.prec = 2
        service = AnalyticsService(session, env.alice)
        summary = service.spending_summary(AnalyticsQuery(**DATES)).currencies[0]
        comparison = service.compare_periods(ComparisonQuery(**DATES)).currencies[0]
        assert summary.total_spent == Decimal("299999999999999.999997")
        assert summary.average_purchase == Decimal("99999999999999.999999")
        assert comparison.absolute_change == Decimal("299999999999999.999996")
    serialized = result(env, "spending-summary")["currencies"][0]
    assert serialized["total_spent"] == "299999999999999.999997"


def test_zero_known_amounts_differ_from_unknown_amounts(analytics):
    env = analytics
    purchase(
        env,
        grand_total="0",
        line_items=[{"raw_name": "Free", "line_total": "0"}, {"raw_name": "Unknown"}],
    )
    summary = result(env, "spending-summary")["currencies"][0]
    assert Decimal(summary["average_purchase"]) == 0 and summary["purchase_count"] == 1
    for basis in ("purchase", "line_item"):
        group = result(env, "spending-by-category", basis=basis)["groups"][0]
        assert Decimal(group["total_amount"]) == 0 and group["share_of_known_total_percent"] is None
        assert group["known_amount_count"] == 1
    assert (
        result(env, "spending-by-category", basis="line_item")["groups"][0]["unknown_amount_count"]
        == 1
    )
    assert result(env, "spending-by-merchant")["groups"][0]["share_of_total_percent"] is None


def test_extraction_evidence_never_becomes_analytics_source(analytics):
    env = analytics
    with env.factory() as session:
        service = PurchaseService(session, env.alice)
        receipt = service.create_receipt(
            ReceiptCreate(
                original_filename="synthetic.png",
                mime_type="image/png",
                file_size=100,
                content_hash="a" * 64,
                source="USER_UPLOAD",
            )
        )
        service.create_extraction_run(
            ExtractionRunCreate(
                receipt_id=receipt.id,
                provider="fixture",
                model="fixture",
                prompt_version="v1",
                schema_version="v1",
                status="SUCCEEDED",
                started_at=NOW,
                completed_at=NOW,
                raw_output={"grand_total": "999999"},
                normalized_output={"grand_total": "999999"},
            )
        )
    assert result(env, "spending-summary")["currencies"] == []
    purchase(env, grand_total="0.30")
    assert Decimal(result(env, "spending-summary")["currencies"][0]["total_spent"]) == Decimal(
        "0.30"
    )


@pytest.mark.parametrize(
    "start_date,end_date,start_at,end_at",
    [
        ("2026-03-08", "2026-03-09", "2026-03-08T05:00:00+00:00", "2026-03-09T04:00:00+00:00"),
        ("2026-11-01", "2026-11-02", "2026-11-01T04:00:00+00:00", "2026-11-02T05:00:00+00:00"),
    ],
)
def test_dst_boundaries_apply_to_history_and_every_analytics_query(
    analytics, start_date, end_date, start_at, end_at
):
    env = analytics
    assert (
        env.client.patch(
            "/api/v1/me/preferences", headers=ALICE, json={"timezone": "America/New_York"}
        ).status_code
        == 200
    )
    start, end = datetime.fromisoformat(start_at), datetime.fromisoformat(end_at)
    purchase(env, purchased_at=start - timedelta(microseconds=1), grand_total="100")
    first = purchase(env, purchased_at=start, grand_total="0.10")
    last = purchase(env, purchased_at=end - timedelta(microseconds=1), grand_total="0.20")
    purchase(env, purchased_at=end, grand_total="200")
    query = {"start_date": start_date, "end_date": end_date}
    summary = result(env, "spending-summary", **query)
    assert summary["period"]["start_at"] == start_at.replace("+00:00", "Z")
    assert summary["period"]["end_at"] == end_at.replace("+00:00", "Z")
    assert summary["currencies"][0]["purchase_count"] == 2
    assert Decimal(summary["currencies"][0]["total_spent"]) == Decimal("0.30")
    assert Decimal(
        result(env, "spending-by-category", **query)["groups"][0]["total_amount"]
    ) == Decimal("0.30")
    assert Decimal(
        result(env, "spending-by-merchant", **query)["groups"][0]["total_spent"]
    ) == Decimal("0.30")
    assert Decimal(
        result(env, "period-comparison", **query)["currencies"][0]["current_total"]
    ) == Decimal("0.30")
    history = env.client.get("/api/v1/purchases", headers=ALICE, params=query).json()["data"]
    assert {row["id"] for row in history} == {str(first.id), str(last.id)}


def test_unrepresentable_calendar_boundary_is_a_safe_api_error(analytics):
    env = analytics
    env.client.patch("/api/v1/me/preferences", headers=ALICE, json={"timezone": "Pacific/Apia"})
    query = {"start_date": "2011-12-30", "end_date": "2011-12-31"}
    for path in [
        *(f"/api/v1/analytics/{endpoint}" for endpoint in ANALYTICS_PATHS),
        "/api/v1/purchases",
    ]:
        response = env.client.get(path, headers=ALICE, params=query)
        assert (
            response.status_code == 422 and response.json()["error"]["code"] == "validation_error"
        )


def test_comparisons_share_a_read_only_snapshot_during_concurrent_commits(analytics, monkeypatch):
    env = analytics
    purchase(env, grand_total="2")
    purchase(env, grand_total="1", purchased_at=datetime(2026, 8, 15, tzinfo=timezone.utc))
    original = AnalyticsRepository.summary
    changed = False

    def interleave(repository, filters, period):
        nonlocal changed
        rows = original(repository, filters, period)
        assert repository._session.scalar(text("SHOW transaction_isolation")) == "repeatable read"
        assert repository._session.scalar(text("SHOW transaction_read_only")) == "on"
        if not changed:
            changed = True
            purchase(env, grand_total="7", purchased_at=datetime(2026, 8, 15, tzinfo=timezone.utc))
            with env.factory() as session:
                UserService(session, env.alice).patch_preferences(
                    PreferencePatch(timezone="America/New_York")
                )
        return rows

    monkeypatch.setattr(AnalyticsRepository, "summary", interleave)
    comparison = result(env, "period-comparison")
    assert (
        comparison["period"]["timezone"]
        == comparison["comparison_period"]["timezone"]
        == "Asia/Kolkata"
    )
    assert Decimal(comparison["currencies"][0]["comparison_total"]) == 1
    subsequent = result(env, "period-comparison")
    assert subsequent["period"]["timezone"] == "America/New_York"
    assert Decimal(subsequent["currencies"][0]["comparison_total"]) == 8
    with env.factory() as session:
        assert session.scalar(text("SHOW transaction_isolation")) == "read committed"
        assert session.scalar(text("SHOW transaction_read_only")) == "off"


def test_database_session_timezone_does_not_change_periods_or_output(analytics):
    env = analytics
    purchase(env, purchased_at=START, grand_total="0.10")
    with env.factory() as session:
        session.execute(text("SET TIME ZONE 'Pacific/Honolulu'"))
        session.commit()
        try:
            view = AnalyticsService(session, env.alice).spending_summary(AnalyticsQuery(**DATES))
            assert view.currencies[0].total_spent == Decimal("0.10")
            assert (
                view.model_dump(mode="json")["currencies"][0]["first_purchased_at"]
                == "2026-08-31T18:30:00Z"
            )
        finally:
            session.execute(text("SET TIME ZONE 'UTC'"))
            session.commit()


def test_indexes_match_owned_analytics_and_child_history_patterns(analytics):
    inspector = inspect(analytics.database)
    purchase_indexes = {
        row["name"]: row["column_names"] for row in inspector.get_indexes("purchases")
    }
    for dimension in ("currency", "merchant", "category"):
        column = dimension if dimension == "currency" else f"{dimension}_id"
        assert purchase_indexes[f"ix_purchases_user_{dimension}_purchased"] == [
            "user_id",
            column,
            "purchased_at",
            "id",
        ]
    line_indexes = {row["name"]: row["column_names"] for row in inspector.get_indexes("line_items")}
    assert line_indexes["ix_line_items_product_purchase"] == ["product_id", "purchase_id"]
    assert line_indexes["ix_line_items_category_purchase"] == ["category_id", "purchase_id"]


def test_local_http_analytics_and_purchase_history_against_postgresql(populated):
    env = populated
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    address, port = listener.getsockname()
    server = uvicorn.Server(uvicorn.Config(env.client.app, log_level="error"))
    thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://{address}:{port}", timeout=15) as client:
            for endpoint in ANALYTICS_PATHS:
                response = client.get(
                    f"/api/v1/analytics/{endpoint}",
                    headers=ALICE,
                    params={**DATES, "currency": "INR"},
                )
                assert response.status_code == 200, response.text
                assert response.headers["Cache-Control"] == "no-store"
                data = response.json()["data"]
                assert data["provenance"] == "DERIVED"
                if endpoint == "spending-summary":
                    assert Decimal(data["currencies"][0]["total_spent"]) == Decimal("13.60")
                elif endpoint == "period-comparison":
                    assert Decimal(data["currencies"][0]["absolute_change"]) == Decimal("-986.40")
                else:
                    amount = "total_amount" if endpoint == "spending-by-category" else "total_spent"
                    assert sum(Decimal(row[amount]) for row in data["groups"]) == Decimal("13.60")
            history = client.get(
                "/api/v1/purchases",
                headers=ALICE,
                params={**DATES, "merchant_id": str(env.store.id), "currency": "INR"},
            )
            assert history.status_code == 200
            assert {row["id"] for row in history.json()["data"]} == {
                str(env.first.id),
                str(env.second.id),
            }
            assert client.get("/api/v1/analytics/spending-summary", params=DATES).status_code == 401
            bob = client.get(
                "/api/v1/analytics/spending-summary",
                headers=BOB,
                params={**DATES, "currency": "INR"},
            )
            assert Decimal(bob.json()["data"]["currencies"][0]["total_spent"]) == 9999
            print(
                "Local PostgreSQL HTTP smoke: four analytics APIs, exact INR 13.60, "
                "filtered history, and isolated owners passed."
            )
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        listener.close()
        assert not thread.is_alive()
