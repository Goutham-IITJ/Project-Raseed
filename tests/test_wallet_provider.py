import base64
import json
from datetime import timedelta
from decimal import Decimal, localcontext
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from google.auth.exceptions import DefaultCredentialsError, RefreshError, TransportError
from m7_fixtures import NOW
from pydantic import ValidationError
from wallet_fixtures import wallet_settings

from backend.app.config import Settings
from backend.app.wallet.google import GoogleWalletProvider, generic_object, retry_after_seconds
from backend.app.wallet.provider import WalletFailure, WalletProjection


def projection():
    ids = GoogleWalletProvider(wallet_settings()).identifiers(UUID(int=1))
    return WalletProjection(*ids, "Merchant <untrusted>", NOW, "INR", Decimal("123.456789"), "PAID")


def provider(handler):
    return GoogleWalletProvider(
        wallet_settings(),
        transport=httpx.MockTransport(handler),
        token_supplier=lambda: "test-token",
    )


def test_generic_mapping_preserves_exact_canonical_values_and_has_no_sensitive_fields():
    with localcontext() as context:
        context.prec = 2
        payload = generic_object(projection())
    assert payload["header"]["defaultValue"]["value"] == "INR 123.456789"
    assert payload["subheader"]["defaultValue"]["value"] == "Merchant <untrusted>"
    assert payload["textModulesData"][2]["body"] == NOW.isoformat()
    assert payload["state"] == "ACTIVE"
    assert set(payload) == {
        "id",
        "classId",
        "state",
        "cardTitle",
        "header",
        "subheader",
        "textModulesData",
    }


@pytest.mark.parametrize("exists,race", [(False, False), (True, False), (False, True)])
def test_class_and_object_upsert_handles_existing_objects_and_insert_races(exists, race):
    sent = []
    patches = 0
    item = projection()

    def handler(request):
        nonlocal patches
        sent.append(request)
        assert request.headers["Authorization"] == "Bearer test-token"
        body = json.loads(request.content)
        if request.url.path.endswith("genericClass"):
            return httpx.Response(409 if exists or race else 200, json={"id": item.class_id})
        assert body == generic_object(item)
        if request.method == "PATCH":
            patches += 1
            if not exists and patches == 1:
                return httpx.Response(404)
        elif race:
            return httpx.Response(409)
        return httpx.Response(200, json={"id": item.object_id, "classId": item.class_id})

    provider(handler).sync(item)
    assert [req.method for req in sent] == (
        ["POST", "PATCH"]
        if exists
        else ["POST", "PATCH", "POST", "PATCH"]
        if race
        else ["POST", "PATCH", "POST"]
    )
    assert all(item.object_id in str(req.url) for req in sent if req.method == "PATCH")


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (400, "wallet_rejected", False),
        (401, "wallet_authorization", False),
        (403, "wallet_authorization", False),
        (404, "wallet_rejected", False),
        (408, "wallet_unavailable", True),
        (429, "wallet_rate_limited", True),
        (500, "wallet_unavailable", True),
        (503, "wallet_unavailable", True),
        (302, "wallet_rejected", False),
    ],
)
def test_provider_error_classification_no_hidden_retries_or_body_leaks(status, code, retryable):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, text="private provider details", headers={"Retry-After": "37"}
        )

    with pytest.raises(WalletFailure) as error:
        provider(handler).sync(projection())
    assert len(calls) == 1
    assert str(error.value) == code
    assert error.value.retryable is retryable
    if status in {429, 500, 503, 408}:
        assert error.value.retry_after == 37


@pytest.mark.parametrize(
    "exception,code",
    [(httpx.ReadTimeout, "wallet_timeout"), (httpx.ConnectError, "wallet_unavailable")],
)
def test_provider_transport_failures(exception, code):
    def handler(request):
        raise exception("sensitive", request=request)

    with pytest.raises(WalletFailure) as error:
        provider(handler).sync(projection())
    assert error.value.code == code and error.value.retryable


@pytest.mark.parametrize(
    "body",
    ["not json", "[]", '{"id":"wrong"}', "x" * 65537],
    ids=["invalid_json", "array", "wrong_id", "oversized"],
)
def test_invalid_google_response_is_permanent(body):
    with pytest.raises(WalletFailure) as error:
        provider(lambda request: httpx.Response(200, text=body)).sync(projection())
    assert error.value.code == "wallet_invalid_response"
    assert not error.value.retryable


def test_object_response_must_match_stable_identifiers():
    def handler(request):
        if request.url.path.endswith("genericClass"):
            return httpx.Response(409)
        return httpx.Response(200, json={"id": projection().object_id, "classId": "foreign"})

    with pytest.raises(WalletFailure, match="wallet_invalid_response"):
        provider(handler).sync(projection())


def test_signed_link_contains_only_existing_pass_reference_and_verifiable_signature():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signed_claims = []

    def encoded(value):
        return base64.urlsafe_b64encode(value).rstrip(b"=")

    def handler(request):
        assert str(request.url) == (
            "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
            "wallet@test-project.iam.gserviceaccount.com:signJwt"
        )
        assert request.method == "POST"
        claims = json.loads(json.loads(request.content)["payload"])
        signed_claims.append(claims)
        data = encoded(b'{"alg":"RS256","typ":"JWT"}') + b"." + encoded(json.dumps(claims).encode())
        signature = key.sign(data, padding.PKCS1v15(), hashes.SHA256())
        return httpx.Response(200, json={"signedJwt": (data + b"." + encoded(signature)).decode()})

    item = projection()
    link = provider(handler).save_link(item.class_id, item.object_id, NOW)
    token = link.removeprefix("https://pay.google.com/gp/v/save/")
    header, body, signature = token.split(".")
    key.public_key().verify(
        base64.urlsafe_b64decode(signature + "=="),
        (header + "." + body).encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    assert signed_claims == [
        {
            "iss": "wallet@test-project.iam.gserviceaccount.com",
            "aud": "google",
            "typ": "savetowallet",
            "iat": int(NOW.timestamp()),
            "exp": int((NOW + timedelta(minutes=5)).timestamp()),
            "origins": ["https://raseed.example"],
            "payload": {"genericObjects": [{"id": item.object_id, "classId": item.class_id}]},
        }
    ]


@pytest.mark.parametrize("token", [None, "", "not-a-jwt", "a.b.c\n", "https://evil.example"])
def test_invalid_signing_response_never_becomes_a_link(token):
    item = projection()
    with pytest.raises(WalletFailure, match="wallet_invalid_response"):
        provider(lambda request: httpx.Response(200, json={"signedJwt": token})).save_link(
            item.class_id, item.object_id, NOW
        )


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, 0),
        ("nonsense", 0),
        ("-1", 0),
        ("86401", 86400),
        ("30", 30),
        ("Thu, 26 Sep 2030 06:00:27 GMT", 27),
        ("Wed, 25 Sep 2030 06:00:00 GMT", 0),
    ],
)
def test_retry_after_is_bounded_and_supports_dates(value, expected):
    assert retry_after_seconds(value, NOW) == expected


def test_configuration_is_lazy_and_ids_are_stable_and_scoped():
    empty = GoogleWalletProvider(Settings(_env_file=None, wallet_issuer_id=""))
    with pytest.raises(WalletFailure, match="wallet_configuration"):
        empty.identifiers(uuid4())
    adapter = GoogleWalletProvider(wallet_settings())
    first = adapter.identifiers(UUID(int=1))
    assert first == adapter.identifiers(UUID(int=1))
    assert first[1] != adapter.identifiers(UUID(int=2))[1]
    with pytest.raises(WalletFailure, match="wallet_configuration"):
        adapter.save_link(first[0], "123456789../evil", NOW)


@pytest.mark.parametrize(
    "changes",
    [
        {"wallet_issuer_id": "../bad"},
        {"wallet_service_account_email": "user@example.com"},
        {"wallet_origins": ["*"]},
        {"wallet_origins": ["https://example.com/path"]},
        {"wallet_origins": ["https://user:password@example.com"]},
        {"wallet_request_timeout_seconds": 31},
    ],
)
def test_wallet_configuration_validation(changes):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **changes)


@pytest.mark.parametrize(
    "exception,code,retryable",
    [
        (DefaultCredentialsError("private credential detail"), "wallet_configuration", False),
        (RefreshError("private credential detail"), "wallet_authorization", False),
        (RefreshError("private credential detail", retryable=True), "wallet_unavailable", True),
        (TransportError("private credential detail"), "wallet_unavailable", True),
    ],
)
def test_adc_failures_are_classified_without_leaking_credentials(
    monkeypatch, exception, code, retryable
):
    def unavailable(**kwargs):
        raise exception

    monkeypatch.setattr("backend.app.wallet.google.google.auth.default", unavailable)
    with pytest.raises(WalletFailure) as error:
        GoogleWalletProvider(wallet_settings()).sync(projection())
    assert str(error.value) == code and error.value.retryable is retryable


@pytest.mark.parametrize("token", [None, "", 42])
def test_missing_access_token_fails_safely(monkeypatch, token):
    class Credentials:
        def refresh(self, request):
            assert request.keywords["timeout"] == 15
            self.token = token

    def default(**kwargs):
        assert "https://www.googleapis.com/auth/wallet_object.issuer" in kwargs["scopes"]
        return Credentials(), "project"

    monkeypatch.setattr("backend.app.wallet.google.google.auth.default", default)
    with pytest.raises(WalletFailure, match="wallet_configuration"):
        GoogleWalletProvider(wallet_settings()).sync(projection())


@pytest.mark.parametrize("field", ["wallet_service_account_email", "wallet_origins"])
def test_missing_signing_configuration_never_calls_google(field):
    settings = wallet_settings().model_copy(update={field: "" if field.endswith("email") else []})

    def unexpected():
        pytest.fail("Credentials must not be requested without signing configuration")

    adapter = GoogleWalletProvider(settings, token_supplier=unexpected)
    item = projection()
    with pytest.raises(WalletFailure, match="wallet_configuration"):
        adapter.save_link(item.class_id, item.object_id, NOW)
