"""receipt.v1: extracted evidence, never a canonical purchase command."""

from datetime import date, time
from typing import Annotated, Literal

from pydantic import Field, field_validator

from backend.app.purchases.schemas import (
    InputModel,
    Money,
    Name,
    PaymentStatus,
    PositiveDecimal,
    currency_code,
)

SCHEMA_VERSION = "receipt.v1"
PROMPT_VERSION = "receipt-extraction.v1"
Confidence = Annotated[float, Field(ge=0, le=1)]
Text = Annotated[str, Field(max_length=500)]


class ProductEvidence(InputModel):
    name: Name | None = None
    brand: Annotated[str, Field(max_length=100)] | None = None
    gtin: Annotated[str, Field(pattern=r"^(?:[0-9]{8}|[0-9]{12,14})$")] | None = None
    source: Literal["OBSERVED", "INFERRED"] | None = None
    confidence: Confidence | None = None


class ExtractedLine(InputModel):
    raw_name: Annotated[str, Field(min_length=1, max_length=500)]
    normalized_name: Text | None = None
    quantity: PositiveDecimal | None = None
    unit: Annotated[str, Field(max_length=40)] | None = None
    unit_price: Money | None = None
    line_total: Money | None = None
    category_suggestion: Text | None = None
    product: ProductEvidence | None = None


class ExtractedPayment(InputModel):
    method: Annotated[str, Field(max_length=40)] | None = None
    amount: PositiveDecimal | None = None
    currency: str | None = None
    last4: Annotated[str, Field(pattern=r"^[0-9]{4}$")] | None = None
    confidence: Confidence | None = None

    @field_validator("currency")
    @classmethod
    def valid_currency(cls, value: str | None) -> str | None:
        return currency_code(value) if value is not None else None


class ReceiptExtractionV1(InputModel):
    schema_version: Literal["receipt.v1"]
    merchant_name: Name | None = None
    merchant_address: Annotated[str, Field(max_length=2000)] | None = None
    purchase_date: date | None = None
    purchase_time: time | None = None
    purchase_timezone: Annotated[str, Field(max_length=100)] | None = None
    purchase_type: Annotated[str, Field(max_length=40)] | None = None
    currency: str | None = None
    subtotal: Money | None = None
    discount_total: Money | None = None
    tax_total: Money | None = None
    shipping_total: Money | None = None
    grand_total: Money | None = None
    payment_status: PaymentStatus = "UNKNOWN"
    payments: Annotated[list[ExtractedPayment], Field(max_length=100)] = Field(default_factory=list)
    line_items: Annotated[list[ExtractedLine], Field(max_length=1000)] = Field(default_factory=list)
    line_total_basis: Literal["SUBTOTAL", "OTHER", "UNKNOWN"] = "UNKNOWN"
    category_suggestion: Text | None = None
    invoice_number: Text | None = None
    language: Annotated[str, Field(max_length=100)] | None = None
    notes: Annotated[str, Field(max_length=5000)] | None = None
    confidence: Confidence | None = None
    financial_source: Literal["OBSERVED", "INFERRED"] | None = None

    @field_validator("currency")
    @classmethod
    def valid_currency(cls, value: str | None) -> str | None:
        return currency_code(value) if value is not None else None
