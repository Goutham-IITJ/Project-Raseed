"""One local fixture identity; never accepts a client-selected account."""

from hmac import compare_digest

from backend.app.config import Settings
from backend.app.identity.context import InvalidToken, VerifiedIdentity

DEMO_TOKEN = "raseed-local-demo-v1"
DEMO_IDENTITY = VerifiedIdentity("raseed-local-demo-v1", "demo@example.test", "Alex Demo")


class LocalDemoVerifier:
    def __init__(self, settings: Settings) -> None:
        # Revalidate even if an internal caller used model_copy/model_construct.
        validated = Settings.model_validate(settings.model_dump())
        if not validated.local_demo:
            raise ValueError("Local demo is disabled")

    def verify(self, token: str) -> VerifiedIdentity:
        if not compare_digest(token.encode(), DEMO_TOKEN.encode()):
            raise InvalidToken
        return DEMO_IDENTITY
