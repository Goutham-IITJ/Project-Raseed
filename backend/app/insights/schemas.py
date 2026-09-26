from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, JsonValue

from backend.app.analytics.schemas import CurrencyComparison, CurrencySummary
from backend.app.inventory.schemas import LotView
from backend.app.purchases.queries import ResolvedPeriod
from backend.app.purchases.schemas import InputModel, PageQuery, View

InsightType = Literal["SPENDING_CHANGE", "UNUSUAL_PURCHASE", "INVENTORY_EXPIRY"]
InsightStatus = Literal["ACTIVE", "READ", "DISMISSED", "RESOLVED", "EXPIRED"]
RULE_VERSION = "insights.v1"


class SpendingSource(BaseModel):
    period: ResolvedPeriod
    comparison_period: ResolvedPeriod
    metrics: CurrencyComparison


class UnusualSource(BaseModel):
    period: ResolvedPeriod
    baseline_period: ResolvedPeriod
    current: CurrencySummary
    baseline: CurrencySummary


class ExpirySource(BaseModel):
    lot: LotView
    as_of_date: date
    timezone: str


class InsightQuery(PageQuery):
    type: InsightType | None = None
    status: InsightStatus | None = None


class InsightUpdate(InputModel):
    status: Literal["READ", "DISMISSED"]
    expected_version: Annotated[int, Field(ge=1, strict=True)]


class InsightView(View):
    id: UUID
    type: InsightType
    title: str
    summary: str
    source_data: dict[str, JsonValue]
    calculation: dict[str, JsonValue]
    provenance: Literal["DERIVED"]
    confidence: Decimal | None
    status: InsightStatus
    version: int
    created_at: datetime
    updated_at: datetime
    evaluated_at: datetime
    expires_at: datetime
    read_at: datetime | None
    dismissed_at: datetime | None


class InsightResponse(View):
    data: InsightView


class InsightListResponse(View):
    data: list[InsightView]
