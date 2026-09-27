import json
from decimal import Decimal

import httpx
import pytest
from m7_fixtures import NOW
from market_fixtures import GTIN, offer

from backend.app.config import Settings
from backend.app.market.ebay import EbayMarketProvider, retry_delay
from backend.app.market.provider import MarketFailure
from backend.app.market.schemas import Identity, MarketQuery


def query(**changes):
    return MarketQuery(
        identity=Identity(name="Acme coffee", gtin=GTIN),
        country="US",
        postal_code="10001",
        currency="USD",
        **changes,
    )


def detail():
    return {
        "itemId": "v1|123|0",
        "title": "Acme coffee",
        "brand": "Acme",
        "gtin": GTIN,
        "mpn": "COFFEE-A",
        "conditionId": "1000",
        "itemWebUrl": "https://www.ebay.com/itm/123",
        "seller": {"username": "example"},
        "price": {"value": "90.123456", "currency": "USD"},
        "itemLocation": {"city": "New York", "country": "US"},
        "localizedAspects": [
            {"name": "Unit Quantity", "value": "500"},
            {"name": "Unit Type", "value": "g"},
            {"name": "Number in Pack", "value": "1"},
            {"name": "Model", "value": "Original"},
        ],
        "shippingOptions": [
            {
                "shippingCost": {"value": "2.50", "currency": "USD"},
                "shipToLocationUsedForEstimate": {"country": "US"},
            }
        ],
        "estimatedAvailabilities": [{"estimatedAvailabilityStatus": "IN_STOCK"}],
    }


def provider(handler, **changes):
    settings = Settings(_env_file=None, market_ebay_token="test-credential", **changes)
    return EbayMarketProvider(settings, transport=httpx.MockTransport(handler), clock=lambda: NOW)


def test_ebay_search_fetches_bounded_fixed_endpoints_and_preserves_source_fields():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer test-credential"
        assert (
            request.headers["X-EBAY-C-ENDUSERCTX"]
            == "contextualLocation=country%3DUS%2Czip%3D10001"
        )
        assert request.url.host == "api.ebay.com"
        assert request.extensions["timeout"]["read"] == 10
        if request.url.path.endswith("/search"):
            assert request.url.params["gtin"] == "04006381333931"
            assert request.url.params["limit"] == "5"
            return httpx.Response(
                200,
                json={
                    "itemSummaries": [
                        {"itemId": "v1|123|0", "itemHref": "https://evil.example/steal"}
                    ]
                },
            )
        assert request.url.path == "/buy/browse/v1/item/v1|123|0"
        return httpx.Response(200, json=detail())

    result = provider(handler).search(query())
    row = result.offers[0]
    assert len(calls) == 2
    assert row.source == "eBay Browse" and row.merchant == "example"
    assert row.price == Decimal("90.123456") and row.shipping == Decimal("2.50") and row.tax is None
    assert row.observed_at == NOW and row.location == "New York, US"
    assert row.delivery_country == "US" and row.pack.count == 1


def test_unknown_structured_pack_or_delivery_remains_unknown_not_title_inference():
    listing = detail()
    listing["title"] = "Acme coffee 500 g pack of 1"
    listing["localizedAspects"] = []
    listing["shippingOptions"] = []
    listing["estimatedAvailabilities"] = []
    adapter = provider(lambda request: httpx.Response(200))
    row = adapter._offer(listing)
    assert row.pack is None and row.delivery_country is None and row.shipping is None
    assert row.availability == "UNKNOWN"


def test_multi_item_lot_does_not_assume_aspects_describe_the_complete_offered_pack():
    listing = detail()
    listing["lotSize"] = 2
    row = provider(lambda request: pytest.fail())._offer(listing)
    assert row.pack is None


def test_empty_results_are_explicit():
    assert (
        provider(lambda request: httpx.Response(200, json={"total": 0})).search(query()).offers
        == []
    )


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (400, "market_rejected", False),
        (401, "market_authorization", False),
        (403, "market_authorization", False),
        (302, "market_rejected", False),
        (408, "market_unavailable", True),
        (429, "market_rate_limited", True),
        (500, "market_unavailable", True),
        (503, "market_unavailable", True),
    ],
)
def test_http_failure_classification_and_no_hidden_retry(status, code, retryable):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, text="private provider credential diagnostic", headers={"Retry-After": "45"}
        )

    with pytest.raises(MarketFailure) as error:
        provider(handler).search(query())
    assert str(error.value) == code and error.value.retryable is retryable
    assert len(calls) == 1
    if retryable:
        assert error.value.retry_after == 45


@pytest.mark.parametrize(
    "exception,code",
    [(httpx.ConnectError, "market_unavailable"), (httpx.ReadTimeout, "market_timeout")],
)
def test_transport_errors(exception, code):
    def handler(request):
        raise exception("sensitive request details", request=request)

    with pytest.raises(MarketFailure, match=code) as error:
        provider(handler).search(query())
    assert error.value.retryable


@pytest.mark.parametrize(
    "body", [[], {}, {"itemSummaries": [{}]}, {"itemSummaries": [{"itemId": "../evil"}]}]
)
def test_malformed_search_payloads_fail_safely(body):
    with pytest.raises(MarketFailure, match="market_invalid_data"):
        provider(lambda request: httpx.Response(200, json=body)).search(query())


@pytest.mark.parametrize(
    "change",
    [
        {"price": {"value": "-1", "currency": "USD"}},
        {"price": {"value": "NaN", "currency": "USD"}},
        {"itemId": "v1|999|0"},
        {"gtin": "invented"},
        {"itemWebUrl": "https://127.0.0.1/"},
        {"seller": {}},
        {"localizedAspects": None},
    ],
)
def test_malformed_detail_never_creates_an_offer(change):
    def handler(request):
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"itemSummaries": [{"itemId": "v1|123|0"}]})
        return httpx.Response(200, json={**detail(), **change})

    with pytest.raises(MarketFailure, match="market_invalid_data"):
        provider(handler).search(query())


@pytest.mark.parametrize(
    "body",
    [b"invalid JSON", b"x" * 131073, b'{"a":' + b"[" * 2000 + b"]" * 2000 + b"}"],
    ids=["json", "oversize", "deeply_nested"],
)
def test_response_size_and_json_limits(body):
    with pytest.raises(MarketFailure, match="market_invalid_data"):
        provider(lambda request: httpx.Response(200, content=body)).search(query())


def test_configuration_is_lazy_and_marketplace_must_match_destination():
    empty = EbayMarketProvider(Settings(_env_file=None, market_ebay_token=""))
    with pytest.raises(MarketFailure, match="market_configuration"):
        empty.search(query())
    with pytest.raises(MarketFailure, match="market_configuration"):
        provider(
            lambda request: pytest.fail("unexpected network"), market_ebay_marketplace="EBAY_GB"
        ).search(query())


def test_provider_does_not_assume_search_identity_matches_and_decodes_decimal_tokens():
    listing = detail()
    listing["gtin"] = "96385074"
    listing["price"]["value"] = 1.25

    def handler(request):
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"itemSummaries": [{"itemId": "v1|123|0"}]})
        return httpx.Response(200, content=json.dumps(listing).encode())

    row = provider(handler).search(query()).offers[0]
    assert row.gtin != offer().gtin and row.price == Decimal("1.25")


@pytest.mark.parametrize(
    "header,expected",
    [(None, 0), ("bad", 0), ("-1", 0), ("999999", 86400), ("Thu, 26 Sep 2030 06:00:30 GMT", 30)],
)
def test_retry_after(header, expected):
    assert retry_delay(header, NOW) == expected


def test_ambiguous_aspects_and_stock_do_not_create_confident_comparisons():
    listing = detail()
    listing["localizedAspects"].append({"name": "Unit Quantity", "value": "250"})
    with pytest.raises(ValueError):
        provider(lambda request: pytest.fail())._offer(listing)
    listing = detail()
    listing["estimatedAvailabilities"].append({"estimatedAvailabilityStatus": "OUT_OF_STOCK"})
    assert provider(lambda request: pytest.fail())._offer(listing).availability == "UNKNOWN"
