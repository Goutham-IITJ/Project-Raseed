import base64
import json
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from ingestion_fixtures import evidence
from pydantic import ValidationError

from backend.app.ingestion.errors import ProcessingError, ReviewRequired
from backend.app.ingestion.gemini import GeminiReceiptExtractor
from backend.app.ingestion.lifecycle import transition
from backend.app.ingestion.normalization import normalized, valid_gtin
from backend.app.ingestion.schema import SCHEMA_VERSION, ReceiptExtractionV1
from backend.app.ingestion.validation import validate_extraction
from backend.app.purchases.models import Receipt


def validate(data):
    return validate_extraction(ReceiptExtractionV1.model_validate(data), uuid4(), "Asia/Kolkata")


def test_schema_and_exact_financial_validation():
    command = validate(evidence())
    assert command.grand_total == Decimal("11.00")
    assert command.line_items[0].quantity == Decimal("2")
    assert command.payments[0].amount == Decimal("11.00")
    assert command.purchased_at.isoformat() == "2026-09-24T04:45:00+00:00"


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "unversioned"},
        {"grand_total": 11.0},
        {"grand_total": True},
        {"grand_total": "NaN"},
        {"grand_total": "Infinity"},
        {"grand_total": "-1"},
        {"grand_total": "100000000000000"},
        {"grand_total": "1.0000001"},
        {"purchase_date": "2026-02-30"},
        {"purchase_time": "25:00"},
        {"currency": "ZZZ"},
        {"line_items": [{"raw_name": "Item", "quantity": "-1"}]},
        {"line_items": [{"raw_name": "Item", "quantity": "0"}]},
        {"line_items": [{"raw_name": "Item", "quantity": "100000000000000"}]},
        {"payments": [{"amount": "-1"}]},
        {"payments": [{"last4": "4111111111111111"}]},
        {"user_id": str(uuid4())},
        {"confidence": 1.1},
    ],
)
def test_schema_rejects_invalid_extracted_facts(change):
    with pytest.raises(ValidationError):
        ReceiptExtractionV1.model_validate(evidence(**change))


@pytest.mark.parametrize(
    "change,code",
    [
        ({"merchant_name": None}, "required_fact_missing"),
        ({"currency": None}, "required_fact_missing"),
        ({"grand_total": None}, "required_fact_missing"),
        ({"purchase_type": None}, "required_fact_missing"),
        ({"purchase_date": None}, "purchase_time_missing"),
        ({"purchase_time": None}, "purchase_time_missing"),
        ({"confidence": None}, "confidence_insufficient"),
        ({"confidence": 0.3}, "confidence_insufficient"),
        ({"financial_source": "INFERRED"}, "financial_source_unverified"),
        ({"grand_total": "12"}, "financial_validation"),
        ({"subtotal": "10.00"}, "line_totals_conflict"),
        ({"purchase_timezone": "Invalid/Zone"}, "timezone_invalid"),
        (
            {
                "purchase_date": "2026-11-01",
                "purchase_time": "01:30",
                "purchase_timezone": "America/New_York",
            },
            "purchase_time_ambiguous",
        ),
        (
            {
                "purchase_date": "2026-03-08",
                "purchase_time": "02:30",
                "purchase_timezone": "America/New_York",
            },
            "purchase_time_ambiguous",
        ),
        (
            {"purchase_time": "10:15+03:00", "purchase_timezone": "Asia/Kolkata"},
            "timezone_conflict",
        ),
    ],
)
def test_business_validation_requires_review(change, code):
    with pytest.raises(ReviewRequired) as failure:
        validate(evidence(**change))
    assert failure.value.code == code


def test_missing_numeric_values_stay_unknown_and_payment_instruments_are_not_invented():
    command = validate(
        evidence(
            subtotal=None,
            discount_total=None,
            tax_total=None,
            shipping_total=None,
            line_items=[{"raw_name": "Item"}],
            payments=[{"method": "CARD", "confidence": 0.99}],
        )
    )
    assert (
        command.subtotal
        is command.discount_total
        is command.tax_total
        is command.shipping_total
        is None
    )
    assert command.line_items[0].quantity is command.line_items[0].unit_price is None
    assert command.payments == []


def test_unreliable_payment_is_retained_as_evidence_but_not_persisted():
    data = evidence(
        payments=[{"method": "CARD", "amount": "1", "currency": "INR", "confidence": 0.2}]
    )
    assert ReceiptExtractionV1.model_validate(data).payments[0].amount == Decimal("1")
    assert validate(data).payments == []


def test_line_totals_are_compared_only_on_explicit_subtotal_basis():
    assert validate(
        evidence(line_total_basis="OTHER", line_items=[{"raw_name": "Item", "line_total": "2"}])
    )
    assert validate(evidence(purchase_time="10:15+05:30")).purchased_at.hour == 4


def test_normalization_is_deterministic_and_gtin_requires_checksum():
    assert normalized("  Ｃorner   SHOP ") == "corner shop"
    assert valid_gtin("4006381333931")
    assert not valid_gtin("4006381333932")
    assert not valid_gtin("guess")


def test_gemini_uses_original_multimodal_bytes_structured_schema_and_configured_model():
    output = json.dumps(evidence())

    def respond(request):
        assert request.url.path == "/v1beta/models/configured-model:generateContent"
        assert not request.url.query
        assert request.headers["x-goog-api-key"] == "test-secret"
        body = json.loads(request.content)
        inline = body["contents"][0]["parts"][0]["inlineData"]
        assert base64.b64decode(inline["data"]) == b"original document"
        assert inline["mimeType"] == "application/pdf"
        assert "untrusted" in body["systemInstruction"]["parts"][0]["text"]
        schema = body["generationConfig"]["responseJsonSchema"]
        assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert request.extensions["timeout"]["read"] == 9
        return httpx.Response(
            200,
            json={
                "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": output}]}}]
            },
        )

    extractor = GeminiReceiptExtractor(
        "test-secret", "configured-model", 9, transport=httpx.MockTransport(respond)
    )
    assert extractor.extract(b"original document", "application/pdf", SCHEMA_VERSION).text == output


@pytest.mark.parametrize(
    "status,retryable",
    [(400, False), (401, False), (403, False), (404, False), (429, True), (500, True), (503, True)],
)
def test_gemini_http_failures_are_classified_and_do_not_leak_provider_content(status, retryable):
    adapter = GeminiReceiptExtractor(
        "secret",
        "model",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status, text="sensitive-provider-detail")
        ),
    )
    with pytest.raises(ProcessingError) as failure:
        adapter.extract(b"image", "image/jpeg", SCHEMA_VERSION)
    assert failure.value.retryable is retryable
    assert "sensitive" not in str(failure.value) and "secret" not in str(failure.value)


@pytest.mark.parametrize(
    "exception,code",
    [(httpx.ReadTimeout, "provider_timeout"), (httpx.ConnectError, "provider_unavailable")],
)
def test_gemini_network_failures_have_no_hidden_retry(exception, code):
    calls = []

    def respond(request):
        calls.append(request)
        raise exception("provider secret")

    adapter = GeminiReceiptExtractor("secret", "model", transport=httpx.MockTransport(respond))
    with pytest.raises(ProcessingError) as failure:
        adapter.extract(b"image", "image/png", SCHEMA_VERSION)
    assert failure.value.code == code and failure.value.retryable
    assert len(calls) == 1


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"candidates": []},
        {"candidates": [{"finishReason": "MAX_TOKENS"}]},
        {"candidates": [{"finishReason": "STOP", "content": {"parts": []}}]},
    ],
)
def test_gemini_rejects_empty_blocked_or_truncated_responses(body):
    adapter = GeminiReceiptExtractor(
        "secret", "model", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    )
    with pytest.raises(ProcessingError, match="complete extraction"):
        adapter.extract(b"image", "image/jpeg", SCHEMA_VERSION)


def test_gemini_missing_configuration_fails_without_network():
    with pytest.raises(ProcessingError) as failure:
        GeminiReceiptExtractor("", "").extract(b"image", "image/jpeg", SCHEMA_VERSION)
    assert failure.value.code == "provider_configuration" and not failure.value.retryable


def test_lifecycle_rejects_skipping_validation_or_reprocessing_success():
    receipt = Receipt(status="UPLOADED")
    with pytest.raises(ValueError):
        transition(receipt, "PROCESSED")
    for state in ("PROCESSING", "EXTRACTED", "VALIDATING", "NORMALIZED", "PROCESSED"):
        transition(receipt, state)
    with pytest.raises(ValueError):
        transition(receipt, "PROCESSING")
