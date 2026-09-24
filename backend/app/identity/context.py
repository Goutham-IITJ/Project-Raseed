from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class VerifiedIdentity:
    """Created only by the token-verification boundary, never from API input."""

    firebase_uid: str
    email: str | None = None
    display_name: str | None = None


@dataclass(frozen=True)
class CurrentUser:
    """Internal ownership capability established after verification/provisioning."""

    id: UUID
    firebase_uid: str


class InvalidToken(Exception):
    pass


class VerificationUnavailable(Exception):
    pass


class TokenVerifier(Protocol):
    def verify(self, token: str) -> VerifiedIdentity: ...
