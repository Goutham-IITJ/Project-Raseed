from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_UP, Decimal, localcontext

import pytest
from pydantic import ValidationError

from backend.app.analytics.money import average, difference, percentage
from backend.app.analytics.schemas import (
    AnalyticsQuery,
    CategoryQuery,
    ComparisonQuery,
    MerchantQuery,
)
from backend.app.purchases.queries import (
    InvalidQuery,
    PeriodQuery,
    PurchaseHistoryQuery,
    date_period,
    preceding_period,
    resolve_period,
)

NOW = datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc)
PATHS = [
    "/api/v1/analytics/spending-summary",
    "/api/v1/analytics/spending-by-category",
    "/api/v1/analytics/spending-by-merchant",
    "/api/v1/analytics/period-comparison",
    "/api/v1/purchases",
]


@pytest.mark.parametrize("path", PATHS)
def test_analytics_requires_authentication_before_query_or_database(unauthenticated_client, path):
    response = unauthenticated_client.get(f"{path}?start_date=bad&user_id=other")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    "values",
    [
        {"start_date": "2026-09-01"},
        {"end_date": "2026-10-01"},
        {"start_date": "2026-09-01", "end_date": "2026-09-01"},
        {"start_date": "2026-10-01", "end_date": "2026-09-01"},
        {"period": "last_month", "start_date": "2026-09-01", "end_date": "2026-10-01"},
        {"period": "last month"},
        {"start_date": "2026-02-29", "end_date": "2026-03-01"},
        {"start_date": "20260901", "end_date": "2026-10-01"},
        {"start_date": "2026-09-01T00:00:00Z", "end_date": "2026-10-01"},
        {"start_date": 1788220800, "end_date": "2026-10-01"},
        {"start_date": datetime(2026, 9, 1), "end_date": date(2026, 10, 1)},
        {"currency": "inr"},
        {"currency": "ZZZ"},
        {"currency": ""},
        {"merchant_id": "not-a-uuid"},
        {"category_id": "not-a-uuid"},
        {"line_item_category_id": "not-a-uuid"},
        {"product_id": "not-a-uuid"},
        {"purchase_type": " "},
        {"purchase_type": "x" * 41},
        {"payment_status": "GUESSED"},
        {"timezone": "UTC"},
        {"user_id": "other"},
        {"sql": "SELECT * FROM purchases"},
    ],
)
def test_rejects_invalid_and_unapproved_query_values(values):
    for model in (AnalyticsQuery, PurchaseHistoryQuery):
        with pytest.raises(ValidationError):
            model.model_validate(values)


@pytest.mark.parametrize(
    "model,values",
    [
        (AnalyticsQuery, {"limit": 10}),
        (CategoryQuery, {"basis": "inferred"}),
        (CategoryQuery, {"limit": 101}),
        (MerchantQuery, {"limit": 0}),
        (MerchantQuery, {"offset": -1}),
        (MerchantQuery, {"offset": 10001}),
        (ComparisonQuery, {"comparison_start_date": "2026-08-01"}),
        (ComparisonQuery, {"comparison_end_date": "2026-09-01"}),
        (
            ComparisonQuery,
            {"comparison_start_date": "2026-09-01", "comparison_end_date": "2026-09-01"},
        ),
    ],
)
def test_endpoint_specific_query_contract(model, values):
    with pytest.raises(ValidationError):
        model.model_validate(values)


@pytest.mark.parametrize(
    "name,start,end",
    [
        ("today", date(2026, 1, 1), date(2026, 1, 2)),
        ("yesterday", date(2025, 12, 31), date(2026, 1, 1)),
        ("this_week", date(2025, 12, 29), date(2026, 1, 5)),
        ("last_week", date(2025, 12, 22), date(2025, 12, 29)),
        ("this_month", date(2026, 1, 1), date(2026, 2, 1)),
        ("last_month", date(2025, 12, 1), date(2026, 1, 1)),
        ("this_year", date(2026, 1, 1), date(2027, 1, 1)),
        ("last_year", date(2025, 1, 1), date(2026, 1, 1)),
    ],
)
def test_allowlisted_calendar_periods_cover_year_boundaries(name, start, end):
    result = resolve_period(PeriodQuery(period=name), "Asia/Kolkata", NOW)
    assert (result.start_date, result.end_date) == (start, end)
    assert result.start_at.hour == result.end_at.hour == 18
    assert result.start_at.minute == result.end_at.minute == 30
    assert result.start_at.date() == start - timedelta(days=1)


def test_periods_use_owner_timezone_and_explicit_default():
    query = PeriodQuery()
    assert resolve_period(query, "Asia/Kolkata", NOW) is None
    current = resolve_period(query, "Asia/Kolkata", NOW, default="this_month")
    western = resolve_period(query, "America/New_York", NOW, default="this_month")
    assert current.start_date == date(2026, 1, 1)
    assert western.start_date == date(2025, 12, 1)
    assert preceding_period(current, "this_month").start_date == date(2025, 12, 1)
    assert preceding_period(current, "this_year").start_date == date(2025, 1, 1)


@pytest.mark.parametrize(
    "start,end,start_hour,end_hour,hours",
    [
        (date(2026, 3, 8), date(2026, 3, 9), 5, 4, 23),
        (date(2026, 11, 1), date(2026, 11, 2), 4, 5, 25),
    ],
)
def test_dst_calendar_days_have_correct_utc_boundaries(start, end, start_hour, end_hour, hours):
    period = date_period(start, end, "America/New_York")
    assert period.start_at == datetime.combine(start, datetime.min.time(), timezone.utc).replace(
        hour=start_hour
    )
    assert period.end_at == datetime.combine(end, datetime.min.time(), timezone.utc).replace(
        hour=end_hour
    )
    assert period.end_at - period.start_at == timedelta(hours=hours)
    previous = preceding_period(period, None)
    assert previous.start_date == start - timedelta(days=1)
    assert previous.end_at == period.start_at


def test_leap_month_and_custom_comparison_length():
    period = resolve_period(
        PeriodQuery(period="last_month"), "UTC", datetime(2024, 3, 31, tzinfo=timezone.utc)
    )
    assert (period.start_date, period.end_date) == (date(2024, 2, 1), date(2024, 3, 1))
    previous = preceding_period(period, "last_month")
    assert (previous.start_date, previous.end_date) == (date(2024, 1, 1), date(2024, 2, 1))
    custom = date_period(date(2026, 9, 1), date(2026, 10, 1), "Asia/Kolkata")
    assert preceding_period(custom, None).start_date == date(2026, 8, 2)


def test_ambiguous_midnight_uses_earliest_occurrence():
    period = date_period(date(2026, 11, 1), date(2026, 11, 2), "America/Havana")
    assert period.start_at == datetime(2026, 11, 1, 4, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "start,end,zone",
    [
        (date(2011, 12, 30), date(2011, 12, 31), "Pacific/Apia"),
        (date(2018, 11, 4), date(2018, 11, 5), "America/Sao_Paulo"),
        (date(1, 1, 1), date(1, 1, 2), "Asia/Kolkata"),
        (date(2026, 1, 1), date(2026, 1, 2), "Not/A_Zone"),
    ],
)
def test_missing_or_unrepresentable_boundaries_fail_explicitly(start, end, zone):
    with pytest.raises(InvalidQuery):
        date_period(start, end, zone)


def test_relative_period_rejects_naive_clock_and_date_overflow():
    with pytest.raises(InvalidQuery):
        resolve_period(PeriodQuery(period="today"), "UTC", datetime(2026, 1, 1))
    with pytest.raises(InvalidQuery):
        resolve_period(
            PeriodQuery(period="this_year"), "UTC", datetime(9999, 12, 31, tzinfo=timezone.utc)
        )
    with pytest.raises(InvalidQuery):
        preceding_period(date_period(date(1, 1, 1), date(1, 2, 1), "UTC"), "this_month")


def test_exact_arithmetic_is_independent_of_decimal_context_and_storage_precision():
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_UP
        assert difference(
            Decimal("999999999999999999999999999999.999999"), Decimal("0.000001")
        ) == Decimal("999999999999999999999999999999.999998")
        assert average(Decimal("0.30"), 3) == Decimal("0.100000")
        assert average(Decimal("0.000001"), 2) == Decimal("0.000000")
        assert average(Decimal("0.000003"), 2) == Decimal("0.000002")
        assert percentage(Decimal("1"), Decimal("3")) == Decimal("33.333333")
        assert percentage(Decimal("-1"), Decimal("3")) == Decimal("-33.333333")
        assert percentage(Decimal("0.000001"), Decimal("200")) == Decimal("0.000000")
        assert percentage(Decimal("0.000003"), Decimal("200")) == Decimal("0.000002")
    assert average(Decimal(0), 0) is None
    assert percentage(Decimal(0), Decimal(0)) is None
    assert percentage(None, Decimal(1)) is None
    assert percentage(Decimal(1), None) is None
