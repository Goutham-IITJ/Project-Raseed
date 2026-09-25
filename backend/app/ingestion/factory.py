from backend.app.config import Settings
from backend.app.ingestion.gemini import GeminiReceiptExtractor
from backend.app.ingestion.storage import CloudStorageProvider, LocalStorageProvider, ObjectStorage


def make_storage(settings: Settings) -> ObjectStorage:
    if settings.storage_provider == "gcs":
        return CloudStorageProvider(settings.gcs_bucket)
    return LocalStorageProvider(settings.local_storage_path)


def make_extractor(settings: Settings) -> GeminiReceiptExtractor:
    return GeminiReceiptExtractor(
        settings.gemini_api_key.get_secret_value(),
        settings.gemini_model,
        settings.extraction_timeout_seconds,
    )
