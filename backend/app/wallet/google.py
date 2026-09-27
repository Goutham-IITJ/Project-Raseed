import json
import math
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from functools import partial
from uuid import UUID

import google.auth
import httpx
from google.auth.exceptions import GoogleAuthError, RefreshError, TransportError
from google.auth.transport.requests import Request

from backend.app.config import Settings
from backend.app.wallet.provider import WalletFailure, WalletProjection

WALLET_URL = "https://walletobjects.googleapis.com/walletobjects/v1/"
IAM_URL = "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
SCOPES = [
    "https://www.googleapis.com/auth/wallet_object.issuer",
    "https://www.googleapis.com/auth/cloud-platform",
]


def retry_after_seconds(value: str | None, now: datetime) -> int:
    if not value:
        return 0
    try:
        seconds = int(value)
    except ValueError:
        try:
            seconds = math.ceil((parsedate_to_datetime(value) - now).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0
    return min(max(seconds, 0), 86400)


class GoogleWalletProvider:
    """Lazy ADC + Generic REST adapter. No provider I/O occurs at construction."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        token_supplier: Callable[[], str] | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.token_supplier = token_supplier or self._access_token

    def identifiers(self, purchase_id: UUID) -> tuple[str, str]:
        issuer = self.settings.wallet_issuer_id
        if not issuer:
            raise WalletFailure("wallet_configuration")
        return f"{issuer}.raseed_receipts_v1", f"{issuer}.raseed_purchase_{purchase_id.hex}"

    def _validate_ids(self, class_id: str, object_id: str) -> None:
        issuer = self.settings.wallet_issuer_id
        if (
            not issuer
            or class_id != f"{issuer}.raseed_receipts_v1"
            or re.fullmatch(re.escape(issuer) + r"\.raseed_purchase_[a-f0-9]{32}", object_id)
            is None
        ):
            raise WalletFailure("wallet_configuration")

    def _access_token(self) -> str:
        try:
            credentials, _ = google.auth.default(scopes=SCOPES)
            credentials.refresh(  # type: ignore[no-untyped-call]
                partial(Request(), timeout=self.settings.wallet_request_timeout_seconds)
            )
        except TransportError as exc:
            raise WalletFailure("wallet_unavailable", retryable=True) from exc
        except RefreshError as exc:
            raise WalletFailure(
                "wallet_unavailable" if exc.retryable else "wallet_authorization",
                retryable=exc.retryable,
            ) from exc
        except GoogleAuthError as exc:
            raise WalletFailure("wallet_configuration") from exc
        if not isinstance(credentials.token, str) or not credentials.token:
            raise WalletFailure("wallet_configuration")
        return credentials.token

    def _client(self) -> httpx.Client:
        return httpx.Client(
            transport=self.transport,
            timeout=self.settings.wallet_request_timeout_seconds,
            follow_redirects=False,
            headers={"Authorization": f"Bearer {self.token_supplier()}"},
        )

    @staticmethod
    def _request(
        client: httpx.Client,
        method: str,
        url: str,
        payload: dict[str, object],
        *,
        allowed: tuple[int, ...] = (),
    ) -> httpx.Response:
        try:
            response = client.request(method, url, json=payload)
        except httpx.TimeoutException as exc:
            raise WalletFailure("wallet_timeout", retryable=True) from exc
        except httpx.RequestError as exc:
            raise WalletFailure("wallet_unavailable", retryable=True) from exc
        status = response.status_code
        if status in allowed or status in (200, 201):
            return response
        if status == 429:
            raise WalletFailure(
                "wallet_rate_limited",
                retryable=True,
                retry_after=retry_after_seconds(
                    response.headers.get("Retry-After"), datetime.now(timezone.utc)
                ),
            )
        if status == 408 or status >= 500:
            raise WalletFailure(
                "wallet_unavailable",
                retryable=True,
                retry_after=retry_after_seconds(
                    response.headers.get("Retry-After"), datetime.now(timezone.utc)
                ),
            )
        if status in (401, 403):
            raise WalletFailure("wallet_authorization")
        raise WalletFailure("wallet_rejected")

    @staticmethod
    def _body(response: httpx.Response) -> dict[str, object]:
        if len(response.content) > 65536:
            raise WalletFailure("wallet_invalid_response")
        try:
            body = response.json()
        except ValueError as exc:
            raise WalletFailure("wallet_invalid_response") from exc
        if not isinstance(body, dict):
            raise WalletFailure("wallet_invalid_response")
        return {str(key): value for key, value in body.items()}

    def sync(self, projection: WalletProjection) -> None:
        self._validate_ids(projection.class_id, projection.object_id)
        payload = generic_object(projection)
        with self._client() as client:
            result = self._request(
                client,
                "POST",
                WALLET_URL + "genericClass",
                {"id": projection.class_id},
                allowed=(409,),
            )
            if result.status_code != 409 and self._body(result).get("id") != projection.class_id:
                raise WalletFailure("wallet_invalid_response")
            object_url = WALLET_URL + "genericObject/" + projection.object_id
            result = self._request(client, "PATCH", object_url, payload, allowed=(404,))
            if result.status_code == 404:
                result = self._request(
                    client, "POST", WALLET_URL + "genericObject", payload, allowed=(409,)
                )
                if result.status_code == 409:
                    result = self._request(client, "PATCH", object_url, payload)
            body = self._body(result)
            if body.get("id") != projection.object_id or body.get("classId") != projection.class_id:
                raise WalletFailure("wallet_invalid_response")

    def save_link(self, class_id: str, object_id: str, now: datetime) -> str:
        self._validate_ids(class_id, object_id)
        signer = self.settings.wallet_service_account_email
        if not signer or not self.settings.wallet_origins:
            raise WalletFailure("wallet_configuration")
        claims = {
            "iss": signer,
            "aud": "google",
            "typ": "savetowallet",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "origins": self.settings.wallet_origins,
            "payload": {"genericObjects": [{"id": object_id, "classId": class_id}]},
        }
        with self._client() as client:
            result = self._request(
                client,
                "POST",
                IAM_URL + signer + ":signJwt",
                {"payload": json.dumps(claims, separators=(",", ":"))},
            )
        token = self._body(result).get("signedJwt")
        if (
            not isinstance(token, str)
            or re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token) is None
        ):
            raise WalletFailure("wallet_invalid_response")
        return "https://pay.google.com/gp/v/save/" + token


def generic_object(projection: WalletProjection) -> dict[str, object]:
    def localized(value: str) -> dict[str, object]:
        return {"defaultValue": {"language": "en-US", "value": value}}

    amount = f"{projection.currency} {projection.total:.6f}"
    return {
        "id": projection.object_id,
        "classId": projection.class_id,
        "state": "ACTIVE",
        "cardTitle": localized("Raseed receipt"),
        "header": localized(amount),
        "subheader": localized(projection.merchant[:80]),
        "textModulesData": [
            {"id": "merchant", "header": "Merchant", "body": projection.merchant},
            {"id": "total", "header": "Recorded total", "body": amount},
            {
                "id": "date",
                "header": "Purchase time (UTC)",
                "body": projection.purchased_at.astimezone(timezone.utc).isoformat(),
            },
            {
                "id": "payment",
                "header": "Recorded payment status",
                "body": projection.payment_status,
            },
        ],
    }
