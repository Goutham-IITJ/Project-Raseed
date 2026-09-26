import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.identity.context import CurrentUser
from backend.app.inventory.models import InventoryEvent
from backend.app.inventory.policy import Eligibility, inventory_eligibility, normalize_unit
from backend.app.inventory.repository import InventoryRepository, LotSnapshot
from backend.app.inventory.schemas import (
    MAX_QUANTITY,
    CandidateView,
    EventCreate,
    EventType,
    EventView,
    EvidenceCorrection,
    ExpiryEvidence,
    ExpiryView,
    ItemView,
    LotCreate,
    LotView,
)
from backend.app.purchases.errors import Conflict, DomainError, NotFound
from backend.app.purchases.models import LineItem
from backend.app.purchases.repositories import PurchaseRepository
from backend.app.purchases.schemas import InputModel, PageQuery


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def request_hash(operation: str, data: InputModel, resource: UUID | None = None) -> str:
    payload = {
        "operation": operation,
        "resource": str(resource),
        "data": data.model_dump(mode="json"),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def event_view(event: InventoryEvent) -> EventView:
    return EventView.model_validate(
        {
            "id": event.id,
            "lot_id": event.lot_id,
            "sequence": event.sequence,
            "event_type": event.event_type,
            "quantity_delta": event.quantity_delta,
            "source": event.source,
            "actor": event.actor,
            "reason": event.reason,
            "created_at": event.created_at,
            "expiry": {
                "date": event.expiry_date,
                "source": event.expiry_source,
                "confidence": event.expiry_confidence,
            }
            if event.expiry_changed
            else None,
        }
    )


class InventoryService:
    def __init__(
        self,
        session: Session,
        current_user: CurrentUser,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.session, self.current_user, self.clock = session, current_user, clock
        self.repository = InventoryRepository(session, current_user)
        self.purchases = PurchaseRepository(session, current_user)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        try:
            with self.session.begin():
                yield
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise Conflict from exc
            raise

    def _lot_view(self, state: LotSnapshot, user_timezone: str) -> LotView:
        today = self.clock().astimezone(ZoneInfo(user_timezone)).date()
        expiry = state.expiry
        provenance: Literal["OBSERVED", "EXTERNAL", "INFERRED", "UNKNOWN"]
        if expiry.source in {"RECEIPT", "USER"}:
            provenance = "OBSERVED"
        elif expiry.source == "PRODUCT_KNOWLEDGE":
            provenance = "EXTERNAL"
        elif expiry.source == "MODEL_ESTIMATE":
            provenance = "INFERRED"
        else:
            provenance = "UNKNOWN"
        status: Literal["UNKNOWN", "NOT_DUE", "DUE", "PAST_DUE"] = "UNKNOWN"
        if expiry.date is not None:
            status = (
                "PAST_DUE" if expiry.date < today else "DUE" if expiry.date == today else "NOT_DUE"
            )
        return LotView(
            id=state.lot.id,
            item_id=state.item.id,
            purchase_id=state.lot.purchase_id,
            line_item_id=state.lot.line_item_id,
            name=state.item.name,
            unit=state.item.unit,
            acquired_at=state.lot.acquired_at,
            quantity_acquired=state.acquired,
            quantity_remaining=state.remaining,
            version=state.version,
            expiry=ExpiryView(**expiry.model_dump(), provenance=provenance, status=status),
            created_at=state.lot.created_at,
        )

    def list_items(self, page: PageQuery) -> list[ItemView]:
        with self.transaction():
            return self.repository.items(page)

    def get_item(self, item_id: UUID) -> ItemView:
        with self.transaction():
            rows = self.repository.items(PageQuery(), item_id)
            if not rows:
                raise NotFound
            return rows[0]

    def list_lots(self, page: PageQuery, item_id: UUID | None = None) -> list[LotView]:
        with self.transaction():
            if item_id is not None and not self.repository.items(PageQuery(), item_id):
                raise NotFound
            zone = self.repository.timezone()
            return [
                self._lot_view(state, zone)
                for state in self.repository.snapshots(page=page, item_id=item_id)
            ]

    def get_lot(self, lot_id: UUID) -> LotView:
        with self.transaction():
            return self._lot_view(self.repository.snapshot(lot_id), self.repository.timezone())

    def list_events(self, lot_id: UUID, page: PageQuery) -> list[EventView]:
        with self.transaction():
            return [event_view(event) for event in self.repository.events(lot_id, page)]

    def candidates(self, purchase_id: UUID) -> list[CandidateView]:
        with self.transaction():
            purchase = self.purchases.get(purchase_id)
            result = []
            for line in purchase.line_items:
                eligibility = self._eligibility(line)
                lot = self.repository.lot_for_line(line.id)
                result.append(
                    CandidateView(
                        line_item_id=line.id,
                        lot_id=lot.id if lot else None,
                        eligible=eligibility.eligible and lot is None,
                        reason="ALREADY_TRACKED" if lot else eligibility.reason,
                        eligibility_source=eligibility.source,
                        quantity=line.quantity,
                        unit=line.unit,
                        raw_name=line.raw_name,
                    )
                )
            return result

    def _eligibility(self, line: LineItem) -> Eligibility:
        flag, source = self.repository.classification(line)
        return inventory_eligibility(flag, source, line.quantity, line.unit)

    def _prior(self, key: UUID, digest: str) -> InventoryEvent | None:
        prior = self.repository.prior(key)
        if prior is not None and prior.request_hash != digest:
            raise Conflict
        return prior

    def _append(
        self,
        *,
        lot_id: UUID,
        sequence: int,
        event_type: EventType,
        delta: Decimal,
        key: UUID,
        digest: str,
        reason: str,
        expiry: ExpiryEvidence | None,
        source: Literal["PURCHASE", "USER", "SERVICE"],
    ) -> InventoryEvent:
        event = InventoryEvent(
            user_id=self.current_user.id,
            lot_id=lot_id,
            sequence=sequence,
            event_type=event_type,
            quantity_delta=delta,
            source=source,
            actor="USER" if source == "USER" else "INVENTORY_WORKER",
            actor_user_id=self.current_user.id if source == "USER" else None,
            reason=reason,
            idempotency_key=key,
            request_hash=digest,
            expiry_changed=expiry is not None,
            expiry_date=expiry.date if expiry else None,
            expiry_source=expiry.source if expiry else None,
            expiry_confidence=expiry.confidence if expiry else None,
        )
        self.repository.append(event)
        return event

    def create_lot(self, data: LotCreate) -> LotView:
        data = LotCreate.model_validate(data.model_dump())
        digest = request_hash("enroll", data)
        unit = normalize_unit(data.unit)
        if not unit or len(unit) > 40:
            raise DomainError
        with self.transaction():
            user = self.repository.lock_owner()
            line = self.purchases.get_line_item(data.line_item_id)
            prior = self._prior(data.idempotency_key, digest)
            if prior is not None:
                return self._lot_view(self.repository.snapshot(prior.lot_id), user.timezone)
            if self.repository.lot_for_line(line.id) is not None:
                raise Conflict
            purchase = self.purchases.get(line.purchase_id)
            lot = self.repository.create_lot(line, purchase, unit)
            self._append(
                lot_id=lot.id,
                sequence=1,
                event_type="PURCHASED",
                delta=data.quantity,
                key=data.idempotency_key,
                digest=digest,
                reason=data.reason,
                expiry=data.expiry,
                source="USER",
            )
            return self._lot_view(self.repository.snapshot(lot.id), user.timezone)

    def record_event(self, lot_id: UUID, data: EventCreate) -> EventView:
        data = EventCreate.model_validate(data.model_dump())
        digest = request_hash("event", data, lot_id)
        with self.transaction():
            self.repository.lock_owner()
            state = self.repository.snapshot(lot_id)
            prior = self._prior(data.idempotency_key, digest)
            if prior is not None:
                return event_view(prior)
            if state.version != data.expected_version:
                raise Conflict
            if data.event_type == "CORRECTION":
                delta = (
                    data.quantity_remaining - state.remaining
                    if data.quantity_remaining is not None
                    else Decimal(0)
                )
            elif data.event_type == "MANUAL_ADJUSTMENT":
                assert data.quantity_delta is not None
                delta = data.quantity_delta
            else:
                assert data.quantity is not None
                delta = -data.quantity
            if not Decimal(0) <= state.remaining + delta <= MAX_QUANTITY:
                raise Conflict
            return event_view(
                self._append(
                    lot_id=lot_id,
                    sequence=state.version + 1,
                    event_type=data.event_type,
                    delta=delta,
                    key=data.idempotency_key,
                    digest=digest,
                    reason=data.reason,
                    expiry=data.expiry,
                    source="USER",
                )
            )

    def record_expiry_evidence(self, lot_id: UUID, data: EvidenceCorrection) -> EventView:
        """Trusted internal enrichment boundary; no public provider/source impersonation."""
        data = EvidenceCorrection.model_validate(data.model_dump())
        digest = request_hash("expiry_evidence", data, lot_id)
        if data.expiry.source == "USER":
            raise DomainError
        with self.transaction():
            self.repository.lock_owner()
            state = self.repository.snapshot(lot_id)
            prior = self._prior(data.idempotency_key, digest)
            if prior is not None:
                return event_view(prior)
            if state.version != data.expected_version:
                raise Conflict
            return event_view(
                self._append(
                    lot_id=lot_id,
                    sequence=state.version + 1,
                    event_type="CORRECTION",
                    delta=Decimal(0),
                    key=data.idempotency_key,
                    digest=digest,
                    reason=data.reason,
                    expiry=data.expiry,
                    source="SERVICE",
                )
            )

    def apply_purchase(self, purchase_id: UUID) -> None:
        """Called inside the worker's event transaction; never commits independently."""
        self.repository.lock_owner()
        purchase = self.purchases.get(purchase_id)
        for line in purchase.line_items:
            if self.repository.lot_for_line(line.id) or not self._eligibility(line).eligible:
                continue
            assert line.quantity is not None and line.unit is not None
            lot = self.repository.create_lot(line, purchase, normalize_unit(line.unit))
            key = uuid5(NAMESPACE_URL, f"raseed:inventory:purchased:{line.id}")
            self._append(
                lot_id=lot.id,
                sequence=1,
                event_type="PURCHASED",
                delta=line.quantity,
                key=key,
                digest=hashlib.sha256(f"purchase:{line.id}".encode()).hexdigest(),
                reason="Acquired from an eligible canonical purchase line.",
                expiry=ExpiryEvidence(),
                source="PURCHASE",
            )
