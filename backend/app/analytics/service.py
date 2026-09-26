from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.analytics.money import ZERO, average, difference, percentage
from backend.app.analytics.repository import AnalyticsRepository
from backend.app.analytics.schemas import (
    AnalyticsQuery,
    CategoryGroup,
    CategoryQuery,
    CategoryView,
    ComparisonQuery,
    ComparisonView,
    CurrencyComparison,
    CurrencySummary,
    MerchantGroup,
    MerchantQuery,
    MerchantView,
    SummaryView,
)
from backend.app.identity.context import CurrentUser
from backend.app.identity.repositories import PreferencesRepository
from backend.app.purchases.queries import (
    PurchaseFilters,
    ResolvedPeriod,
    date_period,
    preceding_period,
    resolve_period,
    utc_now,
)


def _filters(query: PurchaseFilters) -> PurchaseFilters:
    return PurchaseFilters.model_validate(
        query.model_dump(include=set(PurchaseFilters.model_fields))
    )


def _empty_summary(currency: str) -> CurrencySummary:
    return CurrencySummary(
        currency=currency,
        purchase_count=0,
        total_spent=ZERO,
        average_purchase=None,
        smallest_purchase=None,
        largest_purchase=None,
        first_purchased_at=None,
        last_purchased_at=None,
        payment_count=0,
        recorded_payment_total=ZERO,
        purchases_with_recorded_payments=0,
    )


class AnalyticsService:
    """Read-only canonical calculations, reusable by later approved tools."""

    def __init__(
        self,
        session: Session,
        current_user: CurrentUser,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session = session
        self._clock = clock
        self._repository = AnalyticsRepository(session, current_user)
        self._preferences = PreferencesRepository(session, current_user)

    @contextmanager
    def _snapshot(self) -> Iterator[str]:
        with self._session.begin():
            self._repository.start_snapshot()
            yield self._preferences.get().timezone

    def _period(self, query: AnalyticsQuery, timezone_name: str) -> ResolvedPeriod:
        period = resolve_period(query, timezone_name, self._clock(), default="this_month")
        assert period is not None
        return period

    def _summaries(
        self, filters: PurchaseFilters, period: ResolvedPeriod
    ) -> dict[str, CurrencySummary]:
        summaries = {
            row.currency: CurrencySummary(
                **row.model_dump(), average_purchase=average(row.total_spent, row.purchase_count)
            )
            for row in self._repository.summary(filters, period)
        }
        if filters.currency is not None and filters.currency not in summaries:
            summaries[filters.currency] = _empty_summary(filters.currency)
        return summaries

    def spending_summary(self, query: AnalyticsQuery) -> SummaryView:
        with self._snapshot() as timezone_name:
            period = self._period(query, timezone_name)
            filters = _filters(query)
            summaries = self._summaries(filters, period)
            return SummaryView(
                period=period,
                filters=filters,
                currencies=[summaries[currency] for currency in sorted(summaries)],
            )

    def spending_by_category(self, query: CategoryQuery) -> CategoryView:
        with self._snapshot() as timezone_name:
            period = self._period(query, timezone_name)
            rows = self._repository.categories(query, period)
            groups = [
                CategoryGroup(
                    **row.model_dump(exclude={"currency_known_total"}),
                    share_of_known_total_percent=percentage(
                        row.total_amount, row.currency_known_total
                    ),
                )
                for row in rows[: query.limit]
            ]
            return CategoryView(
                period=period,
                filters=_filters(query),
                basis=query.basis,
                groups=groups,
                limit=query.limit,
                offset=query.offset,
                has_more=len(rows) > query.limit,
            )

    def spending_by_merchant(self, query: MerchantQuery) -> MerchantView:
        with self._snapshot() as timezone_name:
            period = self._period(query, timezone_name)
            rows = self._repository.merchants(query, period)
            groups = []
            for row in rows[: query.limit]:
                mean = average(row.total_spent, row.purchase_count)
                assert mean is not None
                groups.append(
                    MerchantGroup(
                        **row.model_dump(exclude={"currency_total"}),
                        average_purchase=mean,
                        share_of_total_percent=percentage(row.total_spent, row.currency_total),
                    )
                )
            return MerchantView(
                period=period,
                filters=_filters(query),
                groups=groups,
                limit=query.limit,
                offset=query.offset,
                has_more=len(rows) > query.limit,
            )

    def compare_periods(self, query: ComparisonQuery) -> ComparisonView:
        with self._snapshot() as timezone_name:
            period = self._period(query, timezone_name)
            if query.comparison_start_date is not None and query.comparison_end_date is not None:
                comparison_period = date_period(
                    query.comparison_start_date, query.comparison_end_date, timezone_name
                )
            else:
                selected = query.period or ("this_month" if query.start_date is None else None)
                comparison_period = preceding_period(period, selected)
            filters = _filters(query)
            current = self._summaries(filters, period)
            previous = self._summaries(filters, comparison_period)
            comparisons = []
            for currency in sorted(current.keys() | previous.keys()):
                now = current.get(currency, _empty_summary(currency))
                before = previous.get(currency, _empty_summary(currency))
                delta = difference(now.total_spent, before.total_spent)
                comparisons.append(
                    CurrencyComparison(
                        currency=currency,
                        current_total=now.total_spent,
                        comparison_total=before.total_spent,
                        absolute_change=delta,
                        percentage_change=percentage(delta, before.total_spent),
                        current_purchase_count=now.purchase_count,
                        comparison_purchase_count=before.purchase_count,
                        purchase_count_change=now.purchase_count - before.purchase_count,
                    )
                )
            return ComparisonView(
                period=period,
                comparison_period=comparison_period,
                filters=filters,
                currencies=comparisons,
            )
