import unicodedata
from typing import TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.identity.context import CurrentUser
from backend.app.purchases.errors import DomainError, NotFound
from backend.app.purchases.models import (
    Category,
    ExtractionRun,
    LineItem,
    Merchant,
    OutboxEvent,
    Payment,
    Product,
    Purchase,
    Receipt,
)
from backend.app.purchases.schemas import (
    CategoryCreate,
    ExtractionRunCreate,
    MerchantCreate,
    PageQuery,
    ProductCreate,
    PurchaseCreate,
    ReceiptCreate,
)


class OwnedRepository:
    def __init__(self, session: Session, current_user: CurrentUser) -> None:
        self._session = session
        self._current_user = current_user


class ReceiptRepository(OwnedRepository):
    def create(self, data: ReceiptCreate) -> Receipt:
        receipt = Receipt(user_id=self._current_user.id, **data.model_dump())
        self._session.add(receipt)
        self._session.flush()
        return receipt

    def get(self, receipt_id: UUID) -> Receipt:
        receipt = self._session.scalar(
            select(Receipt).where(
                Receipt.id == receipt_id, Receipt.user_id == self._current_user.id
            )
        )
        if receipt is None:
            raise NotFound
        return receipt

    def list(self, page: PageQuery) -> list[Receipt]:
        return list(
            self._session.scalars(
                select(Receipt)
                .where(Receipt.user_id == self._current_user.id)
                .order_by(Receipt.created_at.desc(), Receipt.id.desc())
                .limit(page.limit)
                .offset(page.offset)
            )
        )


class ExtractionRunRepository(OwnedRepository):
    def create(self, data: ExtractionRunCreate) -> ExtractionRun:
        ReceiptRepository(self._session, self._current_user).get(data.receipt_id)
        run = ExtractionRun(**data.model_dump())
        self._session.add(run)
        self._session.flush()
        return run

    def get(self, run_id: UUID) -> ExtractionRun:
        run = self._session.scalar(
            select(ExtractionRun)
            .join(Receipt, ExtractionRun.receipt_id == Receipt.id)
            .where(ExtractionRun.id == run_id, Receipt.user_id == self._current_user.id)
        )
        if run is None:
            raise NotFound
        return run


CatalogRecord = TypeVar("CatalogRecord", Merchant, Category, Product)


class CatalogRepository(OwnedRepository):
    """Shared canonical catalog. Authenticated internal access; no public write routes."""

    def _get(self, model: type[CatalogRecord], record_id: UUID) -> CatalogRecord:
        record = self._session.scalar(select(model).where(model.id == record_id))
        if record is None:
            raise NotFound
        return record

    def get_merchant(self, merchant_id: UUID) -> Merchant:
        return self._get(Merchant, merchant_id)

    def get_category(self, category_id: UUID) -> Category:
        return self._get(Category, category_id)

    def get_product(self, product_id: UUID) -> Product:
        return self._get(Product, product_id)

    def create_merchant(self, data: MerchantCreate) -> Merchant:
        normalized = " ".join(unicodedata.normalize("NFKC", data.canonical_name).split()).casefold()
        if len(normalized) > 255:
            raise DomainError
        merchant = Merchant(**data.model_dump(), normalized_name=normalized)
        self._session.add(merchant)
        self._session.flush()
        return merchant

    def create_category(self, data: CategoryCreate) -> Category:
        if data.parent_id is not None:
            self.get_category(data.parent_id)
        category = Category(**data.model_dump())
        self._session.add(category)
        self._session.flush()
        return category

    def create_product(self, data: ProductCreate) -> Product:
        if data.category_id is not None:
            self.get_category(data.category_id)
        product = Product(**data.model_dump(exclude={"metadata"}), product_metadata=data.metadata)
        self._session.add(product)
        self._session.flush()
        return product


class PurchaseRepository(OwnedRepository):
    def create(self, data: PurchaseCreate) -> Purchase:
        if data.receipt_id is not None:
            ReceiptRepository(self._session, self._current_user).get(data.receipt_id)
        catalog = CatalogRepository(self._session, self._current_user)
        if data.merchant_id is not None:
            catalog.get_merchant(data.merchant_id)
        category_ids = {
            item.category_id for item in data.line_items if item.category_id is not None
        }
        if data.category_id is not None:
            category_ids.add(data.category_id)
        for category_id in category_ids:
            catalog.get_category(category_id)
        for product_id in {
            item.product_id for item in data.line_items if item.product_id is not None
        }:
            catalog.get_product(product_id)

        purchase = Purchase(
            user_id=self._current_user.id,
            **data.model_dump(exclude={"line_items", "payments"}),
            line_items=[LineItem(**item.model_dump()) for item in data.line_items],
            payments=[Payment(**payment.model_dump()) for payment in data.payments],
        )
        self._session.add(purchase)
        self._session.flush()
        return purchase

    def get(self, purchase_id: UUID) -> Purchase:
        purchase = self._session.scalar(
            select(Purchase)
            .where(Purchase.id == purchase_id, Purchase.user_id == self._current_user.id)
            .options(selectinload(Purchase.line_items), selectinload(Purchase.payments))
        )
        if purchase is None:
            raise NotFound
        return purchase

    def list(self, page: PageQuery) -> list[Purchase]:
        return list(
            self._session.scalars(
                select(Purchase)
                .where(Purchase.user_id == self._current_user.id)
                .options(selectinload(Purchase.line_items), selectinload(Purchase.payments))
                .order_by(Purchase.purchased_at.desc(), Purchase.id.desc())
                .limit(page.limit)
                .offset(page.offset)
            )
        )

    def get_line_item(self, line_item_id: UUID) -> LineItem:
        item = self._session.scalar(
            select(LineItem)
            .join(Purchase, LineItem.purchase_id == Purchase.id)
            .where(LineItem.id == line_item_id, Purchase.user_id == self._current_user.id)
        )
        if item is None:
            raise NotFound
        return item

    def get_payment(self, payment_id: UUID) -> Payment:
        payment = self._session.scalar(
            select(Payment)
            .join(Purchase, Payment.purchase_id == Purchase.id)
            .where(Payment.id == payment_id, Purchase.user_id == self._current_user.id)
        )
        if payment is None:
            raise NotFound
        return payment


class OutboxRepository(OwnedRepository):
    def record_purchase_created(self, purchase_id: UUID) -> None:
        PurchaseRepository(self._session, self._current_user).get(purchase_id)
        self._session.add(
            OutboxEvent(
                user_id=self._current_user.id,
                purchase_id=purchase_id,
                event_type="PURCHASE_CREATED",
                payload={"purchase_id": str(purchase_id)},
            )
        )
        self._session.flush()

    def for_purchase(self, purchase_id: UUID) -> list[OutboxEvent]:
        PurchaseRepository(self._session, self._current_user).get(purchase_id)
        return list(
            self._session.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.purchase_id == purchase_id,
                    OutboxEvent.user_id == self._current_user.id,
                )
            )
        )
