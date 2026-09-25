from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError

from backend.app.ingestion.errors import ReviewRequired
from backend.app.ingestion.schema import ReceiptExtractionV1
from backend.app.purchases.schemas import LineItemCreate, PaymentCreate, PurchaseCreate

MIN_CONFIDENCE = 0.85


def purchase_timestamp(data: ReceiptExtractionV1, user_timezone: str) -> datetime:
    if data.purchase_date is None or data.purchase_time is None:
        raise ReviewRequired(
            "purchase_time_missing", "An observed purchase date and time are required."
        )
    local = datetime.combine(data.purchase_date, data.purchase_time)
    if local.tzinfo is not None and data.purchase_timezone is None:
        return local.astimezone(timezone.utc)
    try:
        zone = ZoneInfo(data.purchase_timezone or user_timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ReviewRequired("timezone_invalid", "Purchase timezone requires review.") from exc
    if local.tzinfo is not None:
        if local.utcoffset() != local.replace(tzinfo=zone).utcoffset():
            raise ReviewRequired("timezone_conflict", "Purchase time and timezone disagree.")
        return local.astimezone(timezone.utc)
    aware = local.replace(tzinfo=zone)
    if (
        aware.utcoffset() != aware.replace(fold=1).utcoffset()
        or aware.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != local
    ):
        raise ReviewRequired("purchase_time_ambiguous", "Purchase time requires timezone review.")
    return aware.astimezone(timezone.utc)


def validate_extraction(
    data: ReceiptExtractionV1,
    receipt_id: UUID,
    user_timezone: str,
) -> PurchaseCreate:
    if data.confidence is None or data.confidence < MIN_CONFIDENCE:
        raise ReviewRequired("confidence_insufficient", "Extraction confidence requires review.")
    if data.financial_source != "OBSERVED":
        raise ReviewRequired("financial_source_unverified", "Financial facts must be observed.")
    if any(
        value is None
        for value in (
            data.merchant_name,
            data.currency,
            data.grand_total,
            data.purchase_type,
        )
    ):
        raise ReviewRequired("required_fact_missing", "Required purchase information is missing.")
    if data.line_total_basis == "SUBTOTAL" and data.line_items and data.subtotal is not None:
        totals = [item.line_total for item in data.line_items]
        if all(total is not None for total in totals):
            if sum((total for total in totals if total is not None), Decimal(0)) != data.subtotal:
                raise ReviewRequired(
                    "line_totals_conflict", "Line totals do not reconcile with subtotal."
                )
    try:
        payments = [
            PaymentCreate(
                method=payment.method,
                amount=payment.amount,
                currency=payment.currency,
                last4=payment.last4,
            )
            for payment in data.payments
            if payment.method is not None
            and payment.amount is not None
            and payment.currency is not None
            and payment.confidence is not None
            and payment.confidence >= MIN_CONFIDENCE
        ]
        return PurchaseCreate.model_validate(
            {
                "receipt_id": receipt_id,
                "merchant_name_raw": data.merchant_name,
                "purchase_type": data.purchase_type,
                "purchased_at": purchase_timestamp(data, user_timezone),
                "currency": data.currency,
                "subtotal": data.subtotal,
                "discount_total": data.discount_total,
                "tax_total": data.tax_total,
                "shipping_total": data.shipping_total,
                "grand_total": data.grand_total,
                "payment_status": data.payment_status,
                "line_items": [
                    LineItemCreate(
                        raw_name=item.raw_name,
                        quantity=item.quantity,
                        unit=item.unit,
                        unit_price=item.unit_price,
                        line_total=item.line_total,
                    )
                    for item in data.line_items
                ],
                "payments": payments,
            }
        )
    except ValidationError as exc:
        raise ReviewRequired(
            "financial_validation", "Canonical purchase validation failed."
        ) from exc
