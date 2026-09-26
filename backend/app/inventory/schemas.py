from datetime import date as Date
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BeforeValidator, Field, field_validator, model_validator

from backend.app.purchases.schemas import (
    InputModel,
    Money,
    PositiveDecimal,
    View,
    exact_decimal,
    nonblank,
)

MAX_QUANTITY = Decimal("99999999999999.999999")
SignedQuantity = Annotated[
    Decimal,
    BeforeValidator(exact_decimal),
    Field(ge=-MAX_QUANTITY, le=MAX_QUANTITY, max_digits=20, decimal_places=6),
]
Confidence = Annotated[
    Decimal, BeforeValidator(exact_decimal), Field(ge=0, le=1, max_digits=7, decimal_places=6)
]
Reason = Annotated[str, Field(min_length=1, max_length=500)]
Unit = Annotated[str, Field(min_length=1, max_length=40)]
ExpirySource = Literal["RECEIPT", "USER", "PRODUCT_KNOWLEDGE", "MODEL_ESTIMATE", "UNKNOWN"]
EventType = Literal[
    "PURCHASED", "CONSUMED", "EXPIRED", "DISCARDED", "RETURNED", "MANUAL_ADJUSTMENT", "CORRECTION"
]


class ExpiryEvidence(InputModel):
    date: Date | None = None
    source: ExpirySource = "UNKNOWN"
    confidence: Confidence | None = None

    @model_validator(mode="after")
    def evidence_required(self) -> "ExpiryEvidence":
        if self.source == "UNKNOWN":
            if self.date is not None or self.confidence is not None:
                raise ValueError("Unknown expiry cannot assert a date or confidence")
        elif self.date is None or self.confidence is None:
            raise ValueError("Known expiry requires both date and confidence")
        return self


class UserExpiry(ExpiryEvidence):
    source: Literal["USER", "UNKNOWN"] = "UNKNOWN"


class LotCreate(InputModel):
    idempotency_key: UUID
    line_item_id: UUID
    quantity: PositiveDecimal
    unit: Unit
    reason: Reason
    expiry: UserExpiry = Field(default_factory=UserExpiry)

    _text = field_validator("unit", "reason")(nonblank)


class EventCreate(InputModel):
    idempotency_key: UUID
    expected_version: Annotated[int, Field(ge=1, strict=True)]
    event_type: Literal[
        "CONSUMED", "EXPIRED", "DISCARDED", "RETURNED", "MANUAL_ADJUSTMENT", "CORRECTION"
    ]
    reason: Reason
    quantity: PositiveDecimal | None = None
    quantity_delta: SignedQuantity | None = None
    quantity_remaining: Money | None = None
    expiry: UserExpiry | None = None

    _reason = field_validator("reason")(nonblank)

    @model_validator(mode="after")
    def event_fields(self) -> "EventCreate":
        if self.event_type == "CORRECTION":
            if self.quantity is not None or self.quantity_delta is not None:
                raise ValueError("Corrections use an absolute remaining quantity")
            if self.quantity_remaining is None and self.expiry is None:
                raise ValueError("Correction requires quantity or expiry evidence")
        elif self.event_type == "MANUAL_ADJUSTMENT":
            if not self.quantity_delta or any(
                value is not None for value in (self.quantity, self.quantity_remaining, self.expiry)
            ):
                raise ValueError("Adjustment requires only a nonzero signed delta")
        elif self.quantity is None or any(
            value is not None
            for value in (self.quantity_delta, self.quantity_remaining, self.expiry)
        ):
            raise ValueError("Removal requires only a positive quantity")
        return self


class EvidenceCorrection(InputModel):
    """Internal evidence boundary, never accepts provider output without validation."""

    idempotency_key: UUID
    expected_version: Annotated[int, Field(ge=1, strict=True)]
    reason: Reason
    expiry: ExpiryEvidence

    _reason = field_validator("reason")(nonblank)


class ExpiryView(ExpiryEvidence):
    provenance: Literal["OBSERVED", "EXTERNAL", "INFERRED", "UNKNOWN"]
    status: Literal["UNKNOWN", "NOT_DUE", "DUE", "PAST_DUE"]


class ItemView(View):
    id: UUID
    name: str
    product_id: UUID | None
    unit: str
    quantity_remaining: Decimal
    lot_count: int
    created_at: datetime


class LotView(View):
    id: UUID
    item_id: UUID
    purchase_id: UUID
    line_item_id: UUID
    name: str
    unit: str
    acquired_at: datetime
    quantity_acquired: Decimal
    quantity_remaining: Decimal
    version: int
    expiry: ExpiryView
    created_at: datetime


class EventView(View):
    id: UUID
    lot_id: UUID
    sequence: int
    event_type: EventType
    quantity_delta: Decimal
    source: Literal["PURCHASE", "USER", "SERVICE"]
    actor: Literal["USER", "INVENTORY_WORKER"]
    reason: str
    expiry: ExpiryEvidence | None
    created_at: datetime


class CandidateView(View):
    line_item_id: UUID
    lot_id: UUID | None
    eligible: bool
    reason: Literal[
        "ELIGIBLE",
        "ALREADY_TRACKED",
        "EXCLUDED",
        "UNKNOWN_ELIGIBILITY",
        "MISSING_QUANTITY",
        "MISSING_UNIT",
    ]
    eligibility_source: Literal["PRODUCT", "CATEGORY", "UNKNOWN"]
    quantity: Decimal | None
    unit: str | None
    raw_name: str


class ItemResponse(View):
    data: ItemView


class ItemListResponse(View):
    data: list[ItemView]


class LotResponse(View):
    data: LotView


class LotListResponse(View):
    data: list[LotView]


class EventResponse(View):
    data: EventView


class EventListResponse(View):
    data: list[EventView]


class CandidateListResponse(View):
    data: list[CandidateView]
