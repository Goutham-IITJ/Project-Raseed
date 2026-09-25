from backend.app.purchases.models import Receipt

TRANSITIONS: dict[str, set[str]] = {
    "PENDING_UPLOAD": {"UPLOADED", "FAILED"},
    "UPLOADED": {"PROCESSING", "FAILED"},
    "PROCESSING": {"EXTRACTED", "NEEDS_REVIEW", "FAILED"},
    "EXTRACTED": {"VALIDATING", "NEEDS_REVIEW", "FAILED"},
    "VALIDATING": {"NORMALIZED", "NEEDS_REVIEW", "FAILED"},
    "NORMALIZED": {"PROCESSED", "FAILED"},
    "FAILED": {"PENDING_UPLOAD", "PROCESSING", "UPLOADED"},
    "NEEDS_REVIEW": {"UPLOADED"},
    "PROCESSED": set(),
}


def transition(receipt: Receipt, target: str) -> None:
    if target not in TRANSITIONS.get(receipt.status, set()):
        raise ValueError(f"Invalid receipt transition: {receipt.status} -> {target}")
    receipt.status = target
