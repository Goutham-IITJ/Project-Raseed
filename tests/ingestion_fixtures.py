import json
from io import BytesIO

from PIL import Image
from pypdf import PdfWriter

from backend.app.ingestion.extractor import ExtractionResult


def evidence(**changes):
    return {
        "schema_version": "receipt.v1",
        "merchant_name": "Corner SHOP",
        "merchant_address": "1 Test Street",
        "purchase_date": "2026-09-24",
        "purchase_time": "10:15:00",
        "currency": "INR",
        "purchase_type": "RETAIL",
        "subtotal": "10.50",
        "discount_total": "0.50",
        "tax_total": "1.00",
        "shipping_total": "0",
        "grand_total": "11.00",
        "payment_status": "PAID",
        "payments": [{"method": "CASH", "amount": "11.00", "currency": "INR", "confidence": 0.99}],
        "line_items": [
            {
                "raw_name": "  Test   item ",
                "quantity": "2",
                "unit_price": "5.25",
                "line_total": "10.50",
            }
        ],
        "line_total_basis": "SUBTOTAL",
        "invoice_number": "TEST-001",
        "language": "en",
        "confidence": 0.99,
        "financial_source": "OBSERVED",
        **changes,
    }


def document(kind="png"):
    output = BytesIO()
    if kind == "pdf":
        pdf = PdfWriter()
        pdf.add_blank_page(width=72, height=72)
        pdf.write(output)
    else:
        Image.new("RGB", (4, 4), "white").save(
            output, format="JPEG" if kind in {"jpg", "jpeg"} else "PNG"
        )
    return output.getvalue()


class FakeExtractor:
    provider = "fixture"
    model = "deterministic-receipt-v1"

    def __init__(self, output=None, error=None):
        self.output = json.dumps(evidence()) if output is None else output
        self.error = error
        self.calls = []

    def extract(self, data, mime_type, schema_version):
        self.calls.append((data, mime_type, schema_version))
        if self.error:
            raise self.error
        return ExtractionResult(self.output)
