from typing import Literal, Protocol

from backend.app.market.schemas import MarketQuery, ProviderResult

FailureCode = Literal[
    "market_configuration",
    "market_authorization",
    "market_unavailable",
    "market_timeout",
    "market_rate_limited",
    "market_invalid_data",
    "market_rejected",
    "market_lease_expired",
]


class MarketFailure(Exception):
    def __init__(self, code: FailureCode, *, retryable: bool = False, retry_after: int = 0) -> None:
        super().__init__(code)
        self.code, self.retryable = code, retryable
        self.retry_after = min(86400, max(0, retry_after))


class MarketProvider(Protocol):
    name: str

    def search(self, query: MarketQuery) -> ProviderResult: ...
