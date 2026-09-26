import hashlib
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select

from backend.app.identity.models import User
from backend.app.inventory.models import InventoryEvent, InventoryItem, InventoryLot
from backend.app.inventory.policy import EligibilitySource
from backend.app.inventory.schemas import ExpiryEvidence, ItemView
from backend.app.purchases.errors import NotFound
from backend.app.purchases.models import Category, LineItem, OutboxEvent, Product, Purchase
from backend.app.purchases.repositories import OwnedRepository
from backend.app.purchases.schemas import PageQuery


@dataclass(frozen=True)
class LotSnapshot:
    lot: InventoryLot
    item: InventoryItem
    acquired: Decimal
    remaining: Decimal
    version: int
    expiry: ExpiryEvidence


class InventoryRepository(OwnedRepository):
    def lock_owner(self) -> User:
        return self._session.scalars(
            select(User).where(User.id == self._current_user.id).with_for_update()
        ).one()

    def timezone(self) -> str:
        return self._session.scalars(
            select(User.timezone).where(User.id == self._current_user.id)
        ).one()

    def prior(self, key: UUID) -> InventoryEvent | None:
        return self._session.scalar(
            select(InventoryEvent).where(
                InventoryEvent.user_id == self._current_user.id,
                InventoryEvent.idempotency_key == key,
            )
        )

    def lot_for_line(self, line_id: UUID) -> InventoryLot | None:
        return self._session.scalar(
            select(InventoryLot).where(
                InventoryLot.user_id == self._current_user.id,
                InventoryLot.line_item_id == line_id,
            )
        )

    def classification(self, line: LineItem) -> tuple[bool | None, EligibilitySource]:
        product = self._session.get(Product, line.product_id) if line.product_id else None
        flag = product.inventory_eligible if product else None
        source: EligibilitySource = "PRODUCT" if flag is not None else "UNKNOWN"
        category_id = line.category_id or (product.category_id if product else None)
        seen: set[UUID] = set()
        while flag is None and category_id is not None and category_id not in seen:
            seen.add(category_id)
            category = self._session.get(Category, category_id)
            if category is None:
                break
            flag = category.inventory_eligible
            if flag is not None:
                source = "CATEGORY"
            category_id = category.parent_id
        return flag, source

    def create_lot(self, line: LineItem, purchase: Purchase, unit: str) -> InventoryLot:
        identity = (
            "product:" + hashlib.sha256(f"{line.product_id}:{unit}".encode()).hexdigest()
            if line.product_id
            else f"line:{line.id}"
        )
        item = self._session.scalar(
            select(InventoryItem).where(
                InventoryItem.user_id == self._current_user.id,
                InventoryItem.identity_key == identity,
            )
        )
        if item is None:
            product = self._session.get(Product, line.product_id) if line.product_id else None
            item = InventoryItem(
                user_id=self._current_user.id,
                identity_key=identity,
                name=product.canonical_name if product else (line.normalized_name or line.raw_name),
                product_id=line.product_id,
                unit=unit,
            )
            self._session.add(item)
            self._session.flush()
        lot = InventoryLot(
            user_id=self._current_user.id,
            item_id=item.id,
            purchase_id=purchase.id,
            line_item_id=line.id,
            acquired_at=purchase.purchased_at,
        )
        self._session.add(lot)
        self._session.flush()
        return lot

    def append(self, event: InventoryEvent) -> None:
        self._session.add(event)
        self._session.flush()
        # Use the stored decimal scale for identical first-delivery/replay responses.
        self._session.refresh(event)
        self._session.add(
            OutboxEvent(
                user_id=self._current_user.id,
                inventory_event_id=event.id,
                event_type="INVENTORY_CHANGED",
                payload={"inventory_event_id": str(event.id), "lot_id": str(event.lot_id)},
            )
        )
        self._session.flush()

    def snapshots(
        self,
        *,
        lot_id: UUID | None = None,
        item_id: UUID | None = None,
        page: PageQuery | None = None,
    ) -> list[LotSnapshot]:
        totals = (
            select(
                InventoryEvent.lot_id,
                func.sum(InventoryEvent.quantity_delta).label("remaining"),
                func.sum(InventoryEvent.quantity_delta)
                .filter(InventoryEvent.event_type == "PURCHASED")
                .label("acquired"),
                func.max(InventoryEvent.sequence).label("version"),
            )
            .where(InventoryEvent.user_id == self._current_user.id)
            .group_by(InventoryEvent.lot_id)
            .subquery()
        )
        expiry = (
            select(InventoryEvent)
            .where(InventoryEvent.user_id == self._current_user.id, InventoryEvent.expiry_changed)
            .distinct(InventoryEvent.lot_id)
            .order_by(InventoryEvent.lot_id, InventoryEvent.sequence.desc())
            .subquery()
        )
        query = (
            select(
                InventoryLot,
                InventoryItem,
                totals.c.acquired,
                totals.c.remaining,
                totals.c.version,
                expiry.c.expiry_date,
                expiry.c.expiry_source,
                expiry.c.expiry_confidence,
            )
            .join(InventoryItem, InventoryItem.id == InventoryLot.item_id)
            .join(totals, totals.c.lot_id == InventoryLot.id)
            .outerjoin(expiry, expiry.c.lot_id == InventoryLot.id)
            .where(InventoryLot.user_id == self._current_user.id)
            .order_by(InventoryLot.created_at.desc(), InventoryLot.id.desc())
        )
        if lot_id is not None:
            query = query.where(InventoryLot.id == lot_id)
        if item_id is not None:
            query = query.where(InventoryLot.item_id == item_id)
        if page is not None:
            query = query.limit(page.limit).offset(page.offset)
        return [
            # One statement supplies both balance and expiry from the same MVCC snapshot.
            LotSnapshot(
                lot,
                item,
                acquired,
                remaining,
                version,
                ExpiryEvidence.model_validate(
                    {
                        "date": expiry_date,
                        "source": expiry_source or "UNKNOWN",
                        "confidence": expiry_confidence,
                    }
                ),
            )
            for (
                lot,
                item,
                acquired,
                remaining,
                version,
                expiry_date,
                expiry_source,
                expiry_confidence,
            ) in self._session.execute(query)
        ]

    def snapshot(self, lot_id: UUID) -> LotSnapshot:
        rows = self.snapshots(lot_id=lot_id)
        if not rows:
            raise NotFound
        return rows[0]

    def items(self, page: PageQuery, item_id: UUID | None = None) -> list[ItemView]:
        query = (
            select(
                InventoryItem,
                func.sum(InventoryEvent.quantity_delta),
                func.count(func.distinct(InventoryLot.id)),
            )
            .join(InventoryLot, InventoryLot.item_id == InventoryItem.id)
            .join(InventoryEvent, InventoryEvent.lot_id == InventoryLot.id)
            .where(InventoryItem.user_id == self._current_user.id)
            .group_by(InventoryItem.id)
            .order_by(InventoryItem.created_at.desc(), InventoryItem.id.desc())
            .limit(page.limit)
            .offset(page.offset)
        )
        if item_id is not None:
            query = query.where(InventoryItem.id == item_id)
        return [
            ItemView(
                id=item.id,
                name=item.name,
                product_id=item.product_id,
                unit=item.unit,
                created_at=item.created_at,
                quantity_remaining=quantity,
                lot_count=count,
            )
            for item, quantity, count in self._session.execute(query)
        ]

    def events(self, lot_id: UUID, page: PageQuery) -> list[InventoryEvent]:
        self.snapshot(lot_id)
        return list(
            self._session.scalars(
                select(InventoryEvent)
                .where(
                    InventoryEvent.user_id == self._current_user.id,
                    InventoryEvent.lot_id == lot_id,
                )
                .order_by(InventoryEvent.sequence.desc())
                .limit(page.limit)
                .offset(page.offset)
            )
        )
