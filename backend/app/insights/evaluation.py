"""Threshold decisions over existing canonical service views; no model arithmetic."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import JsonValue
from sqlalchemy.orm import Session, sessionmaker

from backend.app.analytics.schemas import AnalyticsQuery, ComparisonQuery
from backend.app.analytics.service import AnalyticsService
from backend.app.identity.context import CurrentUser
from backend.app.insights.schemas import (
    RULE_VERSION,
    ExpirySource,
    InsightType,
    SpendingSource,
    UnusualSource,
)
from backend.app.inventory.service import InventoryService
from backend.app.purchases.queries import PeriodQuery, date_period, resolve_period


@dataclass(frozen=True)
class Candidate:
    key: str
    type: InsightType
    source: dict[str, JsonValue]
    calculation: dict[str, JsonValue]
    expires_at: datetime
    confidence: Decimal | None = None


class InsightEvaluation:
    def __init__(
        self, factory: sessionmaker[Session], user: CurrentUser, now: datetime, timezone: str
    ) -> None:
        self.factory, self.user, self.now, self.timezone = factory, user, now, timezone
        self.today = now.astimezone(ZoneInfo(timezone)).date()

    def financial(self) -> list[Candidate]:
        candidates: list[Candidate] = []
        with self.factory() as session:
            analytics = AnalyticsService(session, self.user, clock=lambda: self.now)
            comparison = analytics.compare_periods(ComparisonQuery(period="last_month"))
            current_month = resolve_period(
                PeriodQuery(period="this_month"), self.timezone, self.now, default="this_month"
            )
            assert current_month is not None
            for metrics in comparison.currencies:
                if (
                    metrics.current_purchase_count >= 3
                    and metrics.comparison_purchase_count >= 3
                    and metrics.comparison_total > 0
                    and abs(Fraction(metrics.absolute_change)) * 4
                    >= Fraction(metrics.comparison_total)
                ):
                    candidates.append(
                        Candidate(
                            key=f"spending:{self.timezone}:{comparison.period.start_date}:{metrics.currency}",
                            type="SPENDING_CHANGE",
                            source=SpendingSource(
                                period=comparison.period,
                                comparison_period=comparison.comparison_period,
                                metrics=metrics,
                            ).model_dump(mode="json"),
                            calculation={
                                "version": RULE_VERSION,
                                "rule": "absolute_change_at_least_25_percent",
                                "minimum_purchases_per_period": 3,
                                "threshold_percent": "25",
                            },
                            expires_at=current_month.end_at,
                        )
                    )
            yesterday = self.today - timedelta(days=1)
            recent = analytics.spending_summary(
                AnalyticsQuery(start_date=yesterday, end_date=self.today)
            )
            baseline = analytics.spending_summary(
                AnalyticsQuery(start_date=yesterday - timedelta(days=30), end_date=yesterday)
            )
            baselines = {row.currency: row for row in baseline.currencies}
            next_day = date_period(self.today, self.today + timedelta(days=1), self.timezone).end_at
            for metric in recent.currencies:
                prior = baselines.get(metric.currency)
                if (
                    prior is not None
                    and prior.purchase_count >= 5
                    and prior.total_spent > 0
                    and metric.largest_purchase is not None
                    and Fraction(metric.largest_purchase) * prior.purchase_count
                    >= 3 * Fraction(prior.total_spent)
                ):
                    candidates.append(
                        Candidate(
                            key=f"unusual:{self.timezone}:{yesterday}:{metric.currency}",
                            type="UNUSUAL_PURCHASE",
                            source=UnusualSource(
                                period=recent.period,
                                baseline_period=baseline.period,
                                current=metric,
                                baseline=prior,
                            ).model_dump(mode="json"),
                            calculation={
                                "version": RULE_VERSION,
                                "rule": "largest_at_least_three_times_baseline_mean",
                                "minimum_baseline_purchases": 5,
                                "baseline_days": 30,
                                "threshold_multiple": "3",
                            },
                            expires_at=next_day,
                        )
                    )
        return candidates

    def inventory(self, lot_id: UUID) -> list[Candidate]:
        with self.factory() as session:
            lot = InventoryService(session, self.user, clock=lambda: self.now).get_lot(lot_id)
        if (
            lot.quantity_remaining <= 0
            or lot.expiry.date is None
            or lot.expiry.date > self.today + timedelta(days=3)
        ):
            return []
        return [
            Candidate(
                key=f"expiry:{lot.id}",
                type="INVENTORY_EXPIRY",
                source=ExpirySource(
                    lot=lot, as_of_date=self.today, timezone=self.timezone
                ).model_dump(mode="json"),
                calculation={
                    "version": RULE_VERSION,
                    "rule": "positive_stock_recorded_expiry_within_three_days",
                    "lookahead_days": 3,
                    "inventory_version": lot.version,
                },
                confidence=lot.expiry.confidence,
                expires_at=date_period(
                    self.today, self.today + timedelta(days=1), self.timezone
                ).end_at,
            )
        ]
