from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, model_validator

from backend.app.purchases.queries import (
    CalendarDate,
    PeriodQuery,
    PurchaseFilters,
    ResolvedPeriod,
)
from backend.app.purchases.schemas import PageQuery, aware_utc

UtcTimestamp = Annotated[datetime, AfterValidator(aware_utc)]


class AnalyticsQuery(PeriodQuery, PurchaseFilters):
    pass


class MerchantQuery(AnalyticsQuery, PageQuery):
    pass


class CategoryQuery(MerchantQuery):
    basis: Literal["purchase", "line_item"] = "purchase"


class ComparisonQuery(AnalyticsQuery):
    comparison_start_date: CalendarDate | None = None
    comparison_end_date: CalendarDate | None = None

    @model_validator(mode="after")
    def valid_comparison(self) -> "ComparisonQuery":
        if (self.comparison_start_date is None) != (self.comparison_end_date is None):
            raise ValueError("Supply both comparison boundaries")
        if (
            self.comparison_start_date is not None
            and self.comparison_end_date is not None
            and self.comparison_start_date >= self.comparison_end_date
        ):
            raise ValueError("The comparison end must follow its start")
        return self


class AnalyticsView(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class PurchaseMetrics(AnalyticsView):
    currency: str
    purchase_count: int
    total_spent: Decimal
    smallest_purchase: Decimal | None
    largest_purchase: Decimal | None
    first_purchased_at: UtcTimestamp | None
    last_purchased_at: UtcTimestamp | None
    payment_count: int
    recorded_payment_total: Decimal
    purchases_with_recorded_payments: int


class CurrencySummary(PurchaseMetrics):
    average_purchase: Decimal | None


class AnalysisMetadata(AnalyticsView):
    provenance: Literal["DERIVED"] = "DERIVED"
    period: ResolvedPeriod
    filters: PurchaseFilters


class SummaryView(AnalysisMetadata):
    currencies: list[CurrencySummary]


class CategoryAmounts(AnalyticsView):
    currency: str
    category_id: UUID | None
    category_name: str | None
    category_slug: str | None
    parent_id: UUID | None
    total_amount: Decimal | None
    purchase_count: int
    line_item_count: int | None
    known_amount_count: int
    unknown_amount_count: int


class CategoryGroup(CategoryAmounts):
    share_of_known_total_percent: Decimal | None


class CategoryView(AnalysisMetadata):
    basis: Literal["purchase", "line_item"]
    groups: list[CategoryGroup]
    limit: int
    offset: int
    has_more: bool


class MerchantAmounts(AnalyticsView):
    currency: str
    merchant_id: UUID | None
    merchant_name: str | None
    total_spent: Decimal
    purchase_count: int
    first_purchased_at: UtcTimestamp
    last_purchased_at: UtcTimestamp


class MerchantGroup(MerchantAmounts):
    average_purchase: Decimal
    share_of_total_percent: Decimal | None


class MerchantView(AnalysisMetadata):
    groups: list[MerchantGroup]
    limit: int
    offset: int
    has_more: bool


class CurrencyComparison(AnalyticsView):
    currency: str
    current_total: Decimal
    comparison_total: Decimal
    absolute_change: Decimal
    percentage_change: Decimal | None
    current_purchase_count: int
    comparison_purchase_count: int
    purchase_count_change: int


class ComparisonView(AnalysisMetadata):
    comparison_period: ResolvedPeriod
    currencies: list[CurrencyComparison]


class SummaryResponse(BaseModel):
    data: SummaryView


class CategoryResponse(BaseModel):
    data: CategoryView


class MerchantResponse(BaseModel):
    data: MerchantView


class ComparisonResponse(BaseModel):
    data: ComparisonView


class TrendPoint(AnalyticsView):
    date: date
    currency: str
    total_spent: Decimal
    purchase_count: int


class TrendView(AnalysisMetadata):
    interval: Literal["day", "month"]
    points: list[TrendPoint]


class TrendResponse(BaseModel):
    data: TrendView


class PaymentAmounts(AnalyticsView):
    currency: str
    method: str
    total_amount: Decimal
    payment_count: int


class PaymentGroup(PaymentAmounts):
    share_of_total_percent: Decimal | None


class PaymentView(AnalysisMetadata):
    groups: list[PaymentGroup]


class PaymentResponse(BaseModel):
    data: PaymentView
