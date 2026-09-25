import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from babel.core import get_global
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)


def exact_decimal(value: object) -> object:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError(
            "Use an exact decimal string, integer, or Decimal; floats are not accepted"
        )
    return value


def nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("Text must not be blank")
    return value


def currency_code(value: str) -> str:
    if not re.fullmatch("[A-Z]{3}", value) or value not in get_global("all_currencies"):
        raise ValueError("Unknown uppercase currency code")
    return value


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")
    return value.astimezone(timezone.utc)


Money = Annotated[
    Decimal,
    BeforeValidator(exact_decimal),
    Field(
        ge=0,
        le=Decimal("99999999999999.999999"),
        max_digits=20,
        decimal_places=6,
    ),
]
PositiveDecimal = Annotated[
    Decimal,
    BeforeValidator(exact_decimal),
    Field(gt=0, le=Decimal("99999999999999.999999"), max_digits=20, decimal_places=6),
]
Name = Annotated[str, Field(min_length=1, max_length=255)]
PaymentStatus = Literal["UNKNOWN", "UNPAID", "PARTIALLY_PAID", "PAID"]
ReceiptStatus = Literal[
    "PENDING_UPLOAD",
    "UPLOADED",
    "PROCESSING",
    "EXTRACTED",
    "VALIDATING",
    "NORMALIZED",
    "PROCESSED",
    "NEEDS_REVIEW",
    "FAILED",
]
RunStatus = Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ReceiptCreate(InputModel):
    original_filename: Name
    mime_type: Literal["image/jpeg", "image/png", "image/webp", "application/pdf"]
    file_size: Annotated[int, Field(gt=0, le=9223372036854775807, strict=True)]
    content_hash: Annotated[str, Field(pattern="^[0-9a-f]{64}$")]
    source: Annotated[str, Field(min_length=1, max_length=40)]

    @field_validator("original_filename")
    @classmethod
    def filename_only(cls, value: str) -> str:
        if value in {".", ".."} or any(char in value for char in "/\\"):
            raise ValueError("Supply an original filename, not a path")
        if any(ord(char) < 32 for char in value):
            raise ValueError("Control characters are not allowed")
        return nonblank(value)

    _source = field_validator("source")(nonblank)


class ExtractionRunCreate(InputModel):
    receipt_id: UUID
    provider: Annotated[str, Field(min_length=1, max_length=100)]
    model: Annotated[str, Field(min_length=1, max_length=100)]
    prompt_version: Annotated[str, Field(min_length=1, max_length=100)]
    schema_version: Annotated[str, Field(min_length=1, max_length=100)]
    status: RunStatus = "PENDING"
    raw_output: dict[str, JsonValue] | None = None
    normalized_output: dict[str, JsonValue] | None = None
    error_code: Annotated[str, Field(max_length=100)] | None = None
    error_message: Annotated[str, Field(max_length=10000)] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    _provenance = field_validator("provider", "model", "prompt_version", "schema_version")(nonblank)

    @field_validator("started_at", "completed_at")
    @classmethod
    def utc_time(cls, value: datetime | None) -> datetime | None:
        return aware_utc(value) if value is not None else None

    @model_validator(mode="after")
    def execution_times(self) -> "ExtractionRunCreate":
        if self.status == "PENDING":
            if self.started_at is not None or self.completed_at is not None:
                raise ValueError("Pending runs have no execution timestamps")
        elif self.started_at is None:
            raise ValueError("Execution requires started_at")
        elif self.status == "RUNNING":
            if self.completed_at is not None:
                raise ValueError("Running runs cannot have completed_at")
        elif self.completed_at is None or self.completed_at < self.started_at:
            raise ValueError("Terminal runs require completion at or after their start")
        return self


class MerchantCreate(InputModel):
    canonical_name: Name
    address: Annotated[str, Field(max_length=2000)] | None = None
    city: Annotated[str, Field(max_length=100)] | None = None
    country: Annotated[str, Field(pattern="^[A-Z]{2}$")] | None = None
    latitude: (
        Annotated[
            Decimal,
            BeforeValidator(exact_decimal),
            Field(ge=-90, le=90, max_digits=9, decimal_places=6),
        ]
        | None
    ) = None
    longitude: (
        Annotated[
            Decimal,
            BeforeValidator(exact_decimal),
            Field(ge=-180, le=180, max_digits=9, decimal_places=6),
        ]
        | None
    ) = None
    _name = field_validator("canonical_name")(nonblank)


class CategoryCreate(InputModel):
    parent_id: UUID | None = None
    name: Annotated[str, Field(min_length=1, max_length=100)]
    slug: Annotated[str, Field(max_length=100, pattern="^[a-z0-9]+(-[a-z0-9]+)*$")]
    description: Annotated[str, Field(max_length=2000)] | None = None
    _name = field_validator("name")(nonblank)


class ProductCreate(InputModel):
    canonical_name: Name
    brand: Annotated[str, Field(max_length=100)] | None = None
    category_id: UUID | None = None
    unit_type: Annotated[str, Field(max_length=40)] | None = None
    metadata: dict[str, JsonValue] | None = None
    _name = field_validator("canonical_name")(nonblank)


class LineItemCreate(InputModel):
    product_id: UUID | None = None
    category_id: UUID | None = None
    raw_name: Annotated[str, Field(min_length=1, max_length=500)]
    normalized_name: Annotated[str, Field(max_length=500)] | None = None
    quantity: PositiveDecimal | None = None
    unit: Annotated[str, Field(max_length=40)] | None = None
    unit_price: Money | None = None
    line_total: Money | None = None
    _name = field_validator("raw_name")(nonblank)


class PaymentCreate(InputModel):
    method: Annotated[str, Field(min_length=1, max_length=40)]
    amount: PositiveDecimal
    currency: str
    provider: Annotated[str, Field(max_length=100)] | None = None
    reference: Annotated[str, Field(max_length=200)] | None = None
    last4: Annotated[str, Field(pattern="^[0-9]{4}$")] | None = None
    _method = field_validator("method")(nonblank)
    _currency = field_validator("currency")(currency_code)

    @field_validator("method", "provider", "reference")
    @classmethod
    def no_card_number(cls, value: str | None) -> str | None:
        if value is not None and re.search(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)", value):
            raise ValueError("Payment identifiers must not contain a full card number")
        return value


class PurchaseCreate(InputModel):
    receipt_id: UUID | None = None
    merchant_id: UUID | None = None
    merchant_name_raw: Annotated[str, Field(min_length=1, max_length=500)]
    purchase_type: Annotated[str, Field(min_length=1, max_length=40)]
    category_id: UUID | None = None
    purchased_at: datetime
    currency: str
    subtotal: Money | None = None
    discount_total: Money | None = None
    tax_total: Money | None = None
    shipping_total: Money | None = None
    grand_total: Money
    payment_status: PaymentStatus
    notes: Annotated[str, Field(max_length=10000)] | None = None
    line_items: Annotated[list[LineItemCreate], Field(max_length=1000)] = Field(
        default_factory=list
    )
    payments: Annotated[list[PaymentCreate], Field(max_length=100)] = Field(default_factory=list)
    _text = field_validator("merchant_name_raw", "purchase_type")(nonblank)
    _currency = field_validator("currency")(currency_code)
    _timestamp = field_validator("purchased_at")(aware_utc)

    @model_validator(mode="after")
    def reconcile(self) -> "PurchaseCreate":
        if (
            self.subtotal is not None
            and self.discount_total is not None
            and self.tax_total is not None
            and self.shipping_total is not None
        ):
            expected = self.subtotal - self.discount_total + self.tax_total + self.shipping_total
            if expected != self.grand_total:
                raise ValueError("Explicit purchase totals do not reconcile")
        if any(payment.currency != self.currency for payment in self.payments):
            raise ValueError("Payment currency must match the purchase")
        total_paid = sum((payment.amount for payment in self.payments), Decimal(0))
        if total_paid > self.grand_total:
            raise ValueError("Payments exceed the purchase total")
        if self.payments:
            if self.payment_status == "UNPAID":
                raise ValueError("Unpaid purchases cannot have payment records")
            if self.payment_status == "PAID" and total_paid != self.grand_total:
                raise ValueError("Supplied payments do not match paid status")
            if self.payment_status == "PARTIALLY_PAID" and total_paid >= self.grand_total:
                raise ValueError("Supplied payments do not match partially-paid status")
        return self


class PageQuery(InputModel):
    limit: Annotated[int, Field(ge=1, le=100)] = 20
    offset: Annotated[int, Field(ge=0, le=10000)] = 0


class View(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TimestampView(View):
    id: UUID
    created_at: datetime
    updated_at: datetime


class ReceiptView(TimestampView):
    original_filename: str
    mime_type: str
    file_size: int
    content_hash: str
    source: str
    status: ReceiptStatus
    uploaded_at: datetime | None
    processed_at: datetime | None
    purchase_id: UUID | None = None
    attempt_count: int = 0
    failure_code: str | None = None
    failure_message: str | None = None


class ExtractionRunView(View):
    id: UUID
    receipt_id: UUID
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    status: RunStatus
    raw_output: dict[str, JsonValue] | None
    normalized_output: dict[str, JsonValue] | None
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class MerchantView(TimestampView):
    canonical_name: str
    normalized_name: str
    address: str | None
    city: str | None
    country: str | None
    latitude: Decimal | None
    longitude: Decimal | None


class CategoryView(TimestampView):
    parent_id: UUID | None
    name: str
    slug: str
    description: str | None


class ProductView(TimestampView):
    canonical_name: str
    brand: str | None
    category_id: UUID | None
    unit_type: str | None
    metadata: dict[str, JsonValue] | None = Field(validation_alias="product_metadata")


class LineItemView(TimestampView):
    product_id: UUID | None
    category_id: UUID | None
    raw_name: str
    normalized_name: str | None
    quantity: Decimal | None
    unit: str | None
    unit_price: Decimal | None
    line_total: Decimal | None


class PaymentView(View):
    id: UUID
    method: str
    amount: Decimal
    currency: str
    provider: str | None
    reference: str | None
    last4: str | None
    created_at: datetime


class PurchaseView(TimestampView):
    receipt_id: UUID | None
    merchant_id: UUID | None
    merchant_name_raw: str
    purchase_type: str
    category_id: UUID | None
    purchased_at: datetime
    currency: str
    subtotal: Decimal | None
    discount_total: Decimal | None
    tax_total: Decimal | None
    shipping_total: Decimal | None
    grand_total: Decimal
    payment_status: PaymentStatus
    notes: str | None
    line_items: list[LineItemView]
    payments: list[PaymentView]


class ReceiptResponse(BaseModel):
    data: ReceiptView


class ReceiptListResponse(BaseModel):
    data: list[ReceiptView]


class PurchaseResponse(BaseModel):
    data: PurchaseView


class PurchaseListResponse(BaseModel):
    data: list[PurchaseView]
