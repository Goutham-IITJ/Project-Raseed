"""Explicit live-provider verification without database writes."""

import argparse
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.ingestion.errors import ProcessingError
from backend.app.ingestion.factory import make_extractor
from backend.app.ingestion.schema import SCHEMA_VERSION, ReceiptExtractionV1
from backend.app.ingestion.upload import Upload, validate_upload
from backend.app.ingestion.validation import validate_extraction
from backend.app.purchases.errors import DomainError


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send a selected receipt to Gemini without database writes."
    )
    parser.add_argument("--send-to-gemini", action="store_true", required=True)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--timezone", required=True, help="IANA timezone for receipt-local times.")
    args = parser.parse_args()
    settings = Settings()
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".pdf": "application/pdf",
    }
    with args.file.open("rb") as source:
        binary = source.read(settings.max_upload_bytes + 1)
    upload = Upload(args.file.name, mime.get(args.file.suffix.lower(), ""), binary)
    try:
        validate_upload(upload, settings)
        result = make_extractor(settings).extract(binary, upload.mime_type, SCHEMA_VERSION)
        extracted = ReceiptExtractionV1.model_validate_json(result.text)
        validate_extraction(extracted, uuid4(), args.timezone)
    except (ProcessingError, DomainError) as exc:
        parser.exit(1, f"Verification did not produce a canonical candidate: {exc.code}\n")
    except ValidationError:
        parser.exit(1, "Provider response failed receipt.v1 schema validation.\n")
    print("Gemini receipt.v1 extraction and canonical validation passed; no database writes.")


if __name__ == "__main__":
    main()
