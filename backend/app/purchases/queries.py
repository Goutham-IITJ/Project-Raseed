"""Typed purchase selection and deterministic local-calendar boundaries."""

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BeforeValidator, Field, field_validator, model_validator

from backend.app.purchases.errors import DomainError
from backend.app.purchases.schemas import (
    InputModel,
    PageQuery,
    PaymentStatus,
    currency_code,
    nonblank,
)

PeriodName = Literal[
    "today",
    "yesterday",
    "this_week",
    "last_week",
    "this_month",
    "last_month",
    "this_year",
    "last_year",
]


class InvalidQuery(DomainError):
    message = "Invalid purchase query or calendar boundary."


def calendar_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return date.fromisoformat(value)
    raise ValueError("Use a calendar date in YYYY-MM-DD format")


CalendarDate = Annotated[date, BeforeValidator(calendar_date)]


class PeriodQuery(InputModel):
    period: PeriodName | None = None
    start_date: CalendarDate | None = None
    end_date: CalendarDate | None = None

    @model_validator(mode="after")
    def valid_period(self) -> "PeriodQuery":
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("Supply both date boundaries")
        if self.start_date is not None and self.end_date is not None:
            if self.period is not None:
                raise ValueError("Choose either a named period or explicit dates")
            if self.start_date >= self.end_date:
                raise ValueError("The end date must follow the start date")
        return self


class PurchaseFilters(InputModel):
    currency: str | None = None
    merchant_id: UUID | None = None
    category_id: UUID | None = None
    line_item_category_id: UUID | None = None
    product_id: UUID | None = None
    purchase_type: Annotated[str, Field(min_length=1, max_length=40)] | None = None
    payment_status: PaymentStatus | None = None

    @field_validator("currency")
    @classmethod
    def valid_currency(cls, value: str | None) -> str | None:
        return currency_code(value) if value is not None else None

    @field_validator("purchase_type")
    @classmethod
    def valid_purchase_type(cls, value: str | None) -> str | None:
        return nonblank(value) if value is not None else None


class PurchaseHistoryQuery(PeriodQuery, PurchaseFilters, PageQuery):
    pass


@dataclass(frozen=True)
class ResolvedPeriod:
    start_date: date
    end_date: date
    timezone: str
    start_at: datetime
    end_at: datetime


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _midnight(day: date, zone: ZoneInfo) -> datetime:
    wall = datetime.combine(day, time.min)
    candidates = set()
    for fold in (0, 1):
        candidate = wall.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
        if candidate.astimezone(zone).replace(tzinfo=None) == wall:
            candidates.add(candidate)
    if not candidates:
        # Midnight in a timezone gap must not silently shift the requested date.
        raise InvalidQuery
    return min(candidates)


def date_period(start: date, end: date, timezone_name: str) -> ResolvedPeriod:
    try:
        if start >= end:
            raise InvalidQuery
        zone = ZoneInfo(timezone_name)
        start_at, end_at = _midnight(start, zone), _midnight(end, zone)
        if start_at >= end_at:
            raise InvalidQuery
        return ResolvedPeriod(start, end, timezone_name, start_at, end_at)
    except (ValueError, OverflowError, ZoneInfoNotFoundError) as exc:
        raise InvalidQuery from exc


def _month_start(day: date, offset: int) -> date:
    year, month_index = divmod(day.year * 12 + day.month - 1 + offset, 12)
    return date(year, month_index + 1, 1)


def resolve_period(
    query: PeriodQuery,
    timezone_name: str,
    now: datetime,
    *,
    default: PeriodName | None = None,
) -> ResolvedPeriod | None:
    if query.start_date is not None and query.end_date is not None:
        return date_period(query.start_date, query.end_date, timezone_name)
    selected = query.period or default
    if selected is None:
        return None
    try:
        if now.tzinfo is None or now.utcoffset() is None:
            raise InvalidQuery
        today = now.astimezone(ZoneInfo(timezone_name)).date()
        if selected in ("today", "yesterday"):
            start = today - timedelta(days=selected == "yesterday")
            end = start + timedelta(days=1)
        elif selected in ("this_week", "last_week"):
            start = today - timedelta(days=today.weekday() + (7 if selected == "last_week" else 0))
            end = start + timedelta(days=7)
        elif selected in ("this_month", "last_month"):
            start = _month_start(today, -1 if selected == "last_month" else 0)
            end = _month_start(start, 1)
        else:
            year = today.year - (1 if selected == "last_year" else 0)
            start, end = date(year, 1, 1), date(year + 1, 1, 1)
        return date_period(start, end, timezone_name)
    except (ValueError, OverflowError, ZoneInfoNotFoundError) as exc:
        raise InvalidQuery from exc


def preceding_period(period: ResolvedPeriod, selected: PeriodName | None) -> ResolvedPeriod:
    try:
        end = period.start_date
        if selected in ("this_month", "last_month"):
            start = _month_start(end, -1)
        elif selected in ("this_year", "last_year"):
            start = date(end.year - 1, 1, 1)
        else:
            start = end - (period.end_date - period.start_date)
        return date_period(start, end, period.timezone)
    except (ValueError, OverflowError) as exc:
        raise InvalidQuery from exc
