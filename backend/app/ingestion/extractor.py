from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ExtractionResult:
    text: str


class ReceiptExtractor(Protocol):
    provider: str
    model: str

    def extract(self, data: bytes, mime_type: str, schema_version: str) -> ExtractionResult: ...
