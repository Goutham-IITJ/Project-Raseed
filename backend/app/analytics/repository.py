from decimal import Decimal

from sqlalchemy import Integer, func, literal, select, text

from backend.app.analytics.money import ZERO
from backend.app.analytics.schemas import (
    CategoryAmounts,
    CategoryQuery,
    MerchantAmounts,
    MerchantQuery,
    PurchaseMetrics,
)
from backend.app.purchases.models import Category, LineItem, Merchant, Payment, Purchase
from backend.app.purchases.queries import PurchaseFilters, ResolvedPeriod
from backend.app.purchases.repositories import (
    OwnedRepository,
    matching_line_conditions,
    purchase_conditions,
)


class CategoryAggregate(CategoryAmounts):
    currency_known_total: Decimal | None


class MerchantAggregate(MerchantAmounts):
    currency_total: Decimal


class AnalyticsRepository(OwnedRepository):
    def start_snapshot(self) -> None:
        # Fixed transaction policy, never user/model SQL. Must precede the first read.
        self._session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))

    def summary(self, filters: PurchaseFilters, period: ResolvedPeriod) -> list[PurchaseMetrics]:
        owned = (
            select(Purchase.id, Purchase.currency, Purchase.grand_total, Purchase.purchased_at)
            .where(*purchase_conditions(self._current_user, filters, period))
            .cte("owned_purchases")
        )
        payments = (
            select(
                Payment.purchase_id,
                func.sum(Payment.amount).label("total"),
                func.count().label("count"),
            )
            .join(owned, Payment.purchase_id == owned.c.id)
            .group_by(Payment.purchase_id)
            .subquery()
        )
        statement = (
            select(
                owned.c.currency,
                func.count().label("purchase_count"),
                func.sum(owned.c.grand_total).label("total_spent"),
                func.min(owned.c.grand_total).label("smallest_purchase"),
                func.max(owned.c.grand_total).label("largest_purchase"),
                func.min(owned.c.purchased_at).label("first_purchased_at"),
                func.max(owned.c.purchased_at).label("last_purchased_at"),
                func.coalesce(func.sum(payments.c.count), 0).label("payment_count"),
                func.coalesce(func.sum(payments.c.total), ZERO).label("recorded_payment_total"),
                func.count(payments.c.purchase_id).label("purchases_with_recorded_payments"),
            )
            .select_from(owned)
            .outerjoin(payments, payments.c.purchase_id == owned.c.id)
            .group_by(owned.c.currency)
            .order_by(owned.c.currency)
        )
        return [
            PurchaseMetrics.model_validate(row)
            for row in self._session.execute(statement).mappings()
        ]

    def categories(self, query: CategoryQuery, period: ResolvedPeriod) -> list[CategoryAggregate]:
        by_line = query.basis == "line_item"
        category_id = LineItem.category_id if by_line else Purchase.category_id
        amount = LineItem.line_total if by_line else Purchase.grand_total
        total = func.sum(amount)
        statement = select(
            Purchase.currency,
            category_id.label("category_id"),
            Category.name.label("category_name"),
            Category.slug.label("category_slug"),
            Category.parent_id,
            total.label("total_amount"),
            func.count(func.distinct(Purchase.id)).label("purchase_count"),
            (func.count(LineItem.id) if by_line else literal(None, Integer)).label(
                "line_item_count"
            ),
            func.count(amount).label("known_amount_count"),
            (func.count() - func.count(amount)).label("unknown_amount_count"),
            func.sum(total).over(partition_by=Purchase.currency).label("currency_known_total"),
        ).select_from(Purchase)
        if by_line:
            statement = statement.join(LineItem, LineItem.purchase_id == Purchase.id).where(
                *matching_line_conditions(query)
            )
        statement = (
            statement.outerjoin(Category, Category.id == category_id)
            .where(*purchase_conditions(self._current_user, query, period))
            .group_by(
                Purchase.currency, category_id, Category.name, Category.slug, Category.parent_id
            )
            .order_by(Purchase.currency, total.desc().nulls_last(), category_id.asc().nulls_last())
            .limit(query.limit + 1)
            .offset(query.offset)
        )
        return [
            CategoryAggregate.model_validate(row)
            for row in self._session.execute(statement).mappings()
        ]

    def merchants(self, query: MerchantQuery, period: ResolvedPeriod) -> list[MerchantAggregate]:
        total = func.sum(Purchase.grand_total)
        statement = (
            select(
                Purchase.currency,
                Purchase.merchant_id,
                Merchant.canonical_name.label("merchant_name"),
                total.label("total_spent"),
                func.count().label("purchase_count"),
                func.min(Purchase.purchased_at).label("first_purchased_at"),
                func.max(Purchase.purchased_at).label("last_purchased_at"),
                func.sum(total).over(partition_by=Purchase.currency).label("currency_total"),
            )
            .select_from(Purchase)
            .outerjoin(Merchant, Merchant.id == Purchase.merchant_id)
            .where(*purchase_conditions(self._current_user, query, period))
            .group_by(Purchase.currency, Purchase.merchant_id, Merchant.canonical_name)
            .order_by(Purchase.currency, total.desc(), Purchase.merchant_id.asc().nulls_last())
            .limit(query.limit + 1)
            .offset(query.offset)
        )
        return [
            MerchantAggregate.model_validate(row)
            for row in self._session.execute(statement).mappings()
        ]
