import ipaddress
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from babel.core import get_global
from pydantic import AfterValidator, BaseModel, Field, field_validator, model_validator

from backend.app.ingestion.normalization import valid_gtin
from backend.app.purchases.schemas import (
    InputModel,
    Money,
    PositiveDecimal,
    aware_utc,
    currency_code,
    nonblank,
)

Text = Annotated[str, Field(min_length=1, max_length=500)]


def country_code(value: str) -> str:
    if value not in get_global("territory_currencies"):
        raise ValueError("Unknown destination country")
    return value


Country = Annotated[str, Field(pattern=r"^[A-Z]{2}$"), AfterValidator(country_code)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$"), AfterValidator(currency_code)]
Unit = Literal["g", "kg", "ml", "l", "each"]
MatchStatus = Literal["EXACT", "UNCERTAIN", "MISMATCH"]


def normalize_gtin(value: str | None) -> str | None:
    if value is None:
        return None
    if not valid_gtin(value):
        raise ValueError("Invalid GTIN")
    return value.zfill(14)


class Pack(InputModel):
    quantity: PositiveDecimal
    unit: Unit
    count: Annotated[int, Field(strict=True, ge=1, le=10000)]


class Identity(InputModel):
    name: Text
    brand: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    gtin: Annotated[str, Field(max_length=14)] | None = None
    mpn: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    variant: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    pack: Pack | None = None
    _gtin = field_validator("gtin")(normalize_gtin)
    _name = field_validator("name")(nonblank)

    @field_validator("name", "brand", "mpn", "variant")
    @classmethod
    def safe_text(cls, value: str | None) -> str | None:
        if value is not None:
            if "\x00" in value:
                raise ValueError("Invalid text")
            value.encode("utf-8")
            nonblank(value)
        return value


class SearchCreate(InputModel):
    line_item_id: UUID | None = None
    product_id: UUID | None = None
    country: Country
    postal_code: (
        Annotated[str, Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9 -]+$")] | None
    ) = None

    @field_validator("postal_code")
    @classmethod
    def normalize_postal(cls, value: str | None) -> str | None:
        return nonblank(value.strip()).upper() if value is not None else None

    @model_validator(mode="after")
    def one_target(self) -> "SearchCreate":
        if (self.line_item_id is None) == (self.product_id is None):
            raise ValueError("Supply exactly one target")
        return self


class SearchArguments(InputModel):
    search_id: UUID


class RetrySearch(InputModel):
    pass


class Target(InputModel):
    identity: Identity
    identity_provenance: Literal["OBSERVED", "UNKNOWN"]
    currency: Currency
    unit_price: Money | None = None
    pricing_unit: str | None = None
    purchased_at: datetime | None = None
    price_provenance: Literal["OBSERVED"] = "OBSERVED"


class MarketQuery(InputModel):
    identity: Identity
    country: Country
    postal_code: str | None
    currency: Currency


class Offer(Identity):
    offer_id: Annotated[str, Field(min_length=1, max_length=200)]
    source: Annotated[str, Field(min_length=1, max_length=100)]
    merchant: Text
    url: Annotated[str, Field(min_length=1, max_length=2048)]
    location: Text | None = None
    delivery_country: Country | None = None
    observed_at: datetime
    expires_at: datetime | None = None
    price: Money
    currency: Currency
    shipping: Money | None = None
    tax: Money | None = None
    condition: Literal["NEW", "USED", "UNKNOWN"]
    availability: Literal["IN_STOCK", "OUT_OF_STOCK", "UNKNOWN"]
    _currency = field_validator("currency")(currency_code)
    _observed = field_validator("observed_at")(aware_utc)
    _expiry = field_validator("expires_at")(lambda v: aware_utc(v) if v is not None else v)
    _text = field_validator("offer_id", "source", "merchant")(nonblank)
    _safe_text = field_validator("offer_id", "source", "merchant", "location")(Identity.safe_text)

    @field_validator("url")
    @classmethod
    def public_url(cls, value: str) -> str:
        value.encode("utf-8")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("Invalid URL text")
        parsed = urlsplit(value)
        host = parsed.hostname
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username
            or parsed.password
            or any(character.isspace() for character in value)
            or "." not in host
        ):
            raise ValueError("Expected a public HTTPS source URL")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if host.endswith((".localhost", ".local")):
                raise ValueError("Nonpublic URL") from None
        else:
            if not address.is_global:
                raise ValueError("Nonpublic URL")
        return value

    @model_validator(mode="after")
    def expiry_order(self) -> "Offer":
        if self.expires_at is not None and self.expires_at <= self.observed_at:
            raise ValueError("Expiry must follow observation")
        return self


class ProviderResult(InputModel):
    offers: Annotated[list[Offer], Field(max_length=5)]

    @model_validator(mode="after")
    def unique_offers(self) -> "ProviderResult":
        if len({offer.offer_id for offer in self.offers}) != len(self.offers):
            raise ValueError("Duplicate offer identifiers")
        return self


class Matching(BaseModel):
    status: MatchStatus
    confidence: Decimal
    provenance: Literal["DERIVED"] = "DERIVED"
    rule: str


class Comparison(BaseModel):
    matching: Matching
    comparable: bool
    reasons: list[str]
    conclusion: Literal[
        "LOWER_DISPLAY_PRICE", "EQUAL_DISPLAY_PRICE", "HIGHER_DISPLAY_PRICE", "NOT_COMPARABLE"
    ]
    display_price_difference: Decimal | None = None
    provenance: Literal["DERIVED"] = "DERIVED"
    checkout_savings_known: Literal[False] = False


class ObservationView(BaseModel):
    id: UUID
    search_id: UUID
    product_id: UUID | None
    provider: str
    provenance: Literal["EXTERNAL"] = "EXTERNAL"
    offer: Offer
    fetched_at: datetime
    expires_at: datetime
    stale: bool
    comparison: Comparison


class SearchView(BaseModel):
    id: UUID
    line_item_id: UUID | None
    product_id: UUID | None
    country: str
    postal_code: str | None
    target: Target
    status: Literal["PENDING", "PROCESSING", "RETRY", "SUCCEEDED", "FAILED"]
    attempt_count: int
    failure_code: str | None
    next_attempt_at: datetime
    created_at: datetime
    completed_at: datetime | None
    expires_at: datetime | None
    observations: list[ObservationView]


class SearchResponse(BaseModel):
    data: SearchView


class ObservationResponse(BaseModel):
    data: ObservationView
