from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.identity.context import CurrentUser
from backend.app.purchases.errors import Conflict, DomainError, InvalidReference
from backend.app.purchases.repositories import (
    CatalogRepository,
    ExtractionRunRepository,
    OutboxRepository,
    PurchaseRepository,
    ReceiptRepository,
)
from backend.app.purchases.schemas import (
    CategoryCreate,
    CategoryView,
    ExtractionRunCreate,
    ExtractionRunView,
    MerchantCreate,
    MerchantView,
    PageQuery,
    ProductCreate,
    ProductView,
    PurchaseCreate,
    PurchaseView,
    ReceiptCreate,
    ReceiptView,
)


class PurchaseService:
    """Transaction boundary for validated canonical records; no provider or file I/O."""

    def __init__(self, session: Session, current_user: CurrentUser) -> None:
        self._session = session
        self._receipts = ReceiptRepository(session, current_user)
        self._runs = ExtractionRunRepository(session, current_user)
        self._catalog = CatalogRepository(session, current_user)
        self._purchases = PurchaseRepository(session, current_user)
        self._outbox = OutboxRepository(session, current_user)

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        try:
            with self._session.begin():
                yield
        except IntegrityError as exc:
            code = getattr(exc.orig, "sqlstate", None)
            if code == "23505":
                raise Conflict from exc
            if code == "23503":
                raise InvalidReference from exc
            if code == "23514":
                raise DomainError from exc
            raise

    def create_receipt(self, data: ReceiptCreate) -> ReceiptView:
        with self._transaction():
            return ReceiptView.model_validate(self._receipts.create(data))

    def get_receipt(self, receipt_id: UUID) -> ReceiptView:
        with self._transaction():
            return ReceiptView.model_validate(self._receipts.get(receipt_id))

    def list_receipts(self, page: PageQuery) -> list[ReceiptView]:
        with self._transaction():
            return [ReceiptView.model_validate(receipt) for receipt in self._receipts.list(page)]

    def create_extraction_run(self, data: ExtractionRunCreate) -> ExtractionRunView:
        with self._transaction():
            return ExtractionRunView.model_validate(self._runs.create(data))

    def get_extraction_run(self, run_id: UUID) -> ExtractionRunView:
        with self._transaction():
            return ExtractionRunView.model_validate(self._runs.get(run_id))

    def create_merchant(self, data: MerchantCreate) -> MerchantView:
        with self._transaction():
            return MerchantView.model_validate(self._catalog.create_merchant(data))

    def get_merchant(self, merchant_id: UUID) -> MerchantView:
        with self._transaction():
            return MerchantView.model_validate(self._catalog.get_merchant(merchant_id))

    def create_category(self, data: CategoryCreate) -> CategoryView:
        with self._transaction():
            return CategoryView.model_validate(self._catalog.create_category(data))

    def get_category(self, category_id: UUID) -> CategoryView:
        with self._transaction():
            return CategoryView.model_validate(self._catalog.get_category(category_id))

    def create_product(self, data: ProductCreate) -> ProductView:
        with self._transaction():
            return ProductView.model_validate(self._catalog.create_product(data))

    def get_product(self, product_id: UUID) -> ProductView:
        with self._transaction():
            return ProductView.model_validate(self._catalog.get_product(product_id))

    def create_purchase(self, data: PurchaseCreate) -> PurchaseView:
        # Revalidate the domain command even if a caller used model_copy/model_construct.
        validated = PurchaseCreate.model_validate(data.model_dump())
        with self._transaction():
            purchase = self._purchases.create(validated)
            self._outbox.record_purchase_created(purchase.id)
            return PurchaseView.model_validate(purchase)

    def get_purchase(self, purchase_id: UUID) -> PurchaseView:
        with self._transaction():
            return PurchaseView.model_validate(self._purchases.get(purchase_id))

    def list_purchases(self, page: PageQuery) -> list[PurchaseView]:
        with self._transaction():
            return [
                PurchaseView.model_validate(purchase) for purchase in self._purchases.list(page)
            ]
