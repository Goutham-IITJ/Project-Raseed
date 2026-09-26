from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.inventory.schemas import EventCreate, ExpiryEvidence, LotCreate, UserExpiry


def command(**changes):
    return {
        "idempotency_key": str(uuid4()),
        "expected_version": 1,
        "event_type": "CONSUMED",
        "quantity": "1",
        "reason": "Used one",
        **changes,
    }


@pytest.mark.parametrize(
    "value", [True, 0.1, "NaN", "Infinity", "-1", "0", "1.0000001", "100000000000000"]
)
def test_inventory_quantities_are_positive_exact_and_bounded(value):
    with pytest.raises(ValidationError):
        EventCreate.model_validate(command(quantity=value))


@pytest.mark.parametrize(
    "changes",
    [
        {"event_type": "PURCHASED"},
        {"event_type": "DELETE"},
        {"quantity": None},
        {"quantity_delta": "1"},
        {"quantity_remaining": "0"},
        {"expiry": {}},
        {"user_id": str(uuid4())},
        {"actor": "INVENTORY_WORKER"},
        {"source": "PURCHASE"},
        {"reason": "   "},
        {"expected_version": True},
        {"expected_version": 0},
        {"event_type": "CORRECTION"},
        {"event_type": "CORRECTION", "quantity": None},
        {"event_type": "MANUAL_ADJUSTMENT", "quantity": None, "quantity_delta": "0"},
        {"event_type": "MANUAL_ADJUSTMENT", "quantity_delta": "1"},
    ],
)
def test_user_event_shapes_reject_ambiguous_or_untrusted_fields(changes):
    with pytest.raises(ValidationError):
        EventCreate.model_validate(command(**changes))


@pytest.mark.parametrize(
    "value",
    [
        {"date": "2026-02-30", "source": "USER", "confidence": "1"},
        {"date": "2026-02-01"},
        {"source": "USER"},
        {"source": "RECEIPT", "date": "2026-02-01"},
        {"confidence": "1"},
        {"source": "UNKNOWN", "date": "2026-02-01", "confidence": "0"},
        {"source": "USER", "date": "2026-02-01", "confidence": "1.01"},
        {"source": "USER", "date": "2026-02-01", "confidence": "-0.1"},
        {"source": "USER", "date": "2026-02-01", "confidence": 0.5},
    ],
)
def test_expiry_never_invents_unknown_values_or_accepts_invalid_evidence(value):
    with pytest.raises(ValidationError):
        ExpiryEvidence.model_validate(value)


@pytest.mark.parametrize("source", ["RECEIPT", "MODEL_ESTIMATE", "PRODUCT_KNOWLEDGE"])
def test_public_expiry_cannot_impersonate_internal_evidence(source):
    with pytest.raises(ValidationError):
        UserExpiry.model_validate({"source": source, "date": "2026-10-01", "confidence": "0.8"})


def test_unknown_expiry_and_zero_correction_remain_explicit():
    assert ExpiryEvidence().model_dump() == {"date": None, "source": "UNKNOWN", "confidence": None}
    result = EventCreate.model_validate(
        command(
            event_type="CORRECTION",
            quantity=None,
            quantity_remaining="0",
        )
    )
    assert result.quantity_remaining == Decimal(0)
    assert result.quantity_delta is None
    adjustment = EventCreate.model_validate(
        command(
            event_type="MANUAL_ADJUSTMENT",
            quantity=None,
            quantity_delta="-0.25",
        )
    )
    assert adjustment.quantity_delta == Decimal("-0.25")


@pytest.mark.parametrize("field,value", [("unit", " "), ("quantity", None), ("reason", "")])
def test_manual_enrollment_requires_explicit_known_values(field, value):
    with pytest.raises(ValidationError):
        LotCreate.model_validate(
            {
                "idempotency_key": uuid4(),
                "line_item_id": uuid4(),
                "quantity": "1",
                "unit": "each",
                "reason": "I keep this at home",
                field: value,
            }
        )
