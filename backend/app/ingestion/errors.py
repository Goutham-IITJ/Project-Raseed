from backend.app.purchases.errors import DomainError


class UploadTooLarge(DomainError):
    status_code = 413
    code = "upload_too_large"
    message = "Receipt exceeds the configured size limit."


class UnsupportedReceipt(DomainError):
    status_code = 415
    code = "unsupported_receipt"
    message = "Upload a valid JPEG, PNG, or unencrypted PDF receipt."


class StorageUnavailable(DomainError):
    status_code = 503
    code = "storage_unavailable"
    message = "Private receipt storage is temporarily unavailable."


class LeaseLost(Exception):
    """A newer attempt owns the receipt; this attempt must not mutate it."""


class ProcessingError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class ReviewRequired(ProcessingError):
    pass
