from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.purchases.schemas import (
    CategoryCreate,
    ExtractionRunCreate,
    LineItemCreate,
    MerchantCreate,
    PaymentCreate,
    ProductCreate,
    PurchaseCreate,
    ReceiptCreate,
)


def purchase_data(**overrides):
    return {
        "merchant_name_raw": "Corner shop",
        "purchase_type": "RETAIL",
        "purchased_at": datetime(2026, 9, 24, 10, tzinfo=timezone.utc),
        "currency": "INR",
        "grand_total": "0.30",
        "payment_status": "UNKNOWN",
        **overrides,
    }


def receipt_data(**overrides):
    return {
        "original_filename": "receipt.jpg",
        "mime_type": "image/jpeg",
        "file_size": 1024,
        "content_hash": "a" * 64,
        "source": "USER_UPLOAD",
        **overrides,
    }


@pytest.mark.parametrize(
    "amount", [0.1, True, "NaN", "Infinity", "-0.01", "0.0000001", "100000000000000"]
)
def test_rejects_inexact_invalid_or_excess_precision_money(amount):
    with pytest.raises(ValidationError):
        PurchaseCreate.model_validate(purchase_data(grand_total=amount))


@pytest.mark.parametrize("field", ["subtotal", "discount_total", "tax_total", "shipping_total"])
def test_every_money_field_rejects_binary_float(field):
    with pytest.raises(ValidationError):
        PurchaseCreate.model_validate(purchase_data(**{field: 0.1}))


def test_unknown_financial_values_are_not_fabricated():
    purchase = PurchaseCreate.model_validate(
        purchase_data(line_items=[{"raw_name": "Unidentified item"}])
    )
    assert purchase.grand_total == Decimal("0.30")
    assert purchase.subtotal is None
    assert purchase.discount_total is None
    assert purchase.tax_total is None
    assert purchase.shipping_total is None
    item = purchase.line_items[0]
    assert item.product_id is None
    assert item.quantity is None and item.unit_price is None and item.line_total is None


def test_explicit_totals_reconcile_exactly_without_rounding():
    values = purchase_data(
        subtotal="0.10", discount_total="0", tax_total="0.20", shipping_total="0"
    )
    assert PurchaseCreate.model_validate(values).grand_total == Decimal("0.30")
    with pytest.raises(ValidationError, match="reconcile"):
        PurchaseCreate.model_validate({**values, "grand_total": "0.31"})


@pytest.mark.parametrize(
    "overrides",
    [
        {"currency": "ZZZ"},
        {"currency": "usd"},
        {"purchased_at": datetime(2026, 1, 1)},
        {"merchant_name_raw": " "},
        {"purchase_type": " "},
        {"payment_status": "GUESSED"},
        {"user_id": "client-selected"},
        {"grand_total": None},
    ],
)
def test_purchase_requires_valid_explicit_facts(overrides):
    with pytest.raises(ValidationError):
        PurchaseCreate.model_validate(purchase_data(**overrides))


@pytest.mark.parametrize(
    "overrides",
    [
        {"file_size": 0},
        {"file_size": True},
        {"file_size": "1024"},
        {"content_hash": "not-a-hash"},
        {"content_hash": "A" * 64},
        {"original_filename": "../receipt.jpg"},
        {"original_filename": "..\\receipt.jpg"},
        {"original_filename": "\x00bad.jpg"},
        {"original_filename": " "},
        {"mime_type": "text/html"},
        {"source": " "},
        {"storage_uri": "https://public.example/receipt.jpg"},
        {"status": "PROCESSED"},
        {"user_id": "another-user"},
    ],
)
def test_receipt_metadata_validation(overrides):
    with pytest.raises(ValidationError):
        ReceiptCreate.model_validate(receipt_data(**overrides))


@pytest.mark.parametrize(
    "overrides",
    [
        {"quantity": 0},
        {"quantity": 1.5},
        {"quantity": "0.0000001"},
        {"quantity": "100000000000000"},
        {"unit_price": 0.1},
        {"line_total": 0.1},
        {"line_total": "-1"},
        {"raw_name": " "},
    ],
)
def test_line_item_validation(overrides):
    with pytest.raises(ValidationError):
        LineItemCreate.model_validate({"raw_name": "Item", **overrides})


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": 0.1},
        {"amount": "0"},
        {"amount": "-1"},
        {"amount": "100000000000000"},
        {"currency": "ZZZ"},
        {"last4": "12345"},
        {"last4": "abcd"},
        {"reference": "4111 1111 1111 1111"},
        {"card_number": "4111111111111111"},
        {"cvv": "123"},
    ],
)
def test_payment_validation_and_credential_rejection(overrides):
    with pytest.raises(ValidationError):
        PaymentCreate.model_validate(
            {"method": "CARD", "amount": "0.30", "currency": "INR", **overrides}
        )


@pytest.mark.parametrize(
    "status,amount,currency",
    [
        ("UNKNOWN", "0.31", "INR"),
        ("UNKNOWN", "0.30", "USD"),
        ("UNPAID", "0.10", "INR"),
        ("PAID", "0.10", "INR"),
        ("PARTIALLY_PAID", "0.30", "INR"),
    ],
)
def test_payment_amount_currency_and_status_reconciliation(status, amount, currency):
    with pytest.raises(ValidationError):
        PurchaseCreate.model_validate(
            purchase_data(
                payment_status=status,
                payments=[{"method": "CASH", "amount": amount, "currency": currency}],
            )
        )


def test_partial_payment_and_paid_without_instrument_are_supported():
    assert PurchaseCreate.model_validate(purchase_data(payment_status="PAID")).payments == []
    command = PurchaseCreate.model_validate(
        purchase_data(
            payment_status="PARTIALLY_PAID",
            payments=[{"method": "CASH", "amount": "0.10", "currency": "INR"}],
        )
    )
    assert command.payments[0].amount == Decimal("0.10")


def test_catalog_validation():
    for model, data in [
        (CategoryCreate, {"name": "Category", "slug": "Invalid Slug"}),
        (ProductCreate, {"canonical_name": " "}),
        (MerchantCreate, {"canonical_name": "Shop", "latitude": "91"}),
        (MerchantCreate, {"canonical_name": "Shop", "longitude": "-181"}),
    ]:
        with pytest.raises(ValidationError):
            model.model_validate(data)


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "SUCCEEDED"},
        {"status": "RUNNING"},
        {"status": "UNKNOWN"},
        {"started_at": "2026-09-24T10:00:00Z"},
        {"provider": " "},
        {"status": "RUNNING", "started_at": "2026-09-24T10:00:00"},
        {
            "status": "RUNNING",
            "started_at": "2026-09-24T10:00:00Z",
            "completed_at": "2026-09-24T11:00:00Z",
        },
        {
            "status": "FAILED",
            "started_at": "2026-09-24T10:00:00Z",
            "completed_at": "2026-09-24T09:00:00Z",
        },
    ],
)
def test_extraction_run_requires_consistent_provenance(overrides):
    with pytest.raises(ValidationError):
        ExtractionRunCreate.model_validate(
            {
                "receipt_id": "b9f9d254-dcef-427b-8efb-4ba36eb324ec",
                "provider": "test",
                "model": "test-model",
                "prompt_version": "v1",
                "schema_version": "v1",
                **overrides,
            }
        )
