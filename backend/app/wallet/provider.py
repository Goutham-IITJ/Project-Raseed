from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

FailureCode = Literal[
    "wallet_configuration",
    "wallet_authorization",
    "wallet_timeout",
    "wallet_unavailable",
    "wallet_rate_limited",
    "wallet_invalid_response",
    "wallet_rejected",
    "wallet_lease_expired",
]


class WalletFailure(Exception):
    """Safe codes only; provider response bodies never cross this boundary."""

    def __init__(self, code: FailureCode, *, retryable: bool = False, retry_after: int = 0) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.retry_after = min(max(retry_after, 0), 86400)


@dataclass(frozen=True)
class WalletProjection:
    class_id: str
    object_id: str
    merchant: str
    purchased_at: datetime
    currency: str
    total: Decimal
    payment_status: str


class WalletProvider(Protocol):
    def identifiers(self, purchase_id: UUID) -> tuple[str, str]: ...

    def sync(self, projection: WalletProjection) -> None: ...

    def save_link(self, class_id: str, object_id: str, now: datetime) -> str: ...
