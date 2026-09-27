from datetime import timedelta
from decimal import Decimal, localcontext

import pytest
from m7_fixtures import NOW
from market_fixtures import GTIN, PACK, offer
from pydantic import ValidationError

from backend.app.market.comparison import compare, matching
from backend.app.market.schemas import Identity, Pack, ProviderResult, SearchCreate, Target


def target(**changes):
    return Target.model_validate(
        {
            "identity": {
                "name": "Acme coffee",
                "brand": "Acme",
                "gtin": GTIN,
                "mpn": "COFFEE-A",
                "variant": "Original",
                "pack": PACK,
            },
            "identity_provenance": "OBSERVED",
            "currency": "USD",
            "unit_price": "100",
            "pricing_unit": "each",
            "purchased_at": NOW - timedelta(days=30),
            **changes,
        }
    )


def comparison(candidate=None, baseline=None, **options):
    return compare(
        baseline or target(),
        candidate or offer(),
        "US",
        NOW + timedelta(minutes=15),
        NOW,
        **options,
    )


def test_exact_gtin_and_equivalent_unit_conversion_support_only_display_price_conclusion():
    with localcontext() as context:
        context.prec = 2
        result = comparison(
            offer(price="90.123456", pack={"quantity": "0.5", "unit": "kg", "count": 1})
        )
    assert result.matching.status == "EXACT" and result.matching.confidence == Decimal(1)
    assert result.comparable and result.conclusion == "LOWER_DISPLAY_PRICE"
    assert result.display_price_difference == Decimal("-9.876544")
    assert result.checkout_savings_known is False
    assert result.provenance == "DERIVED"


@pytest.mark.parametrize(
    "price,conclusion",
    [("100", "EQUAL_DISPLAY_PRICE"), ("101", "HIGHER_DISPLAY_PRICE"), ("0", "LOWER_DISPLAY_PRICE")],
)
def test_exact_price_comparison(price, conclusion):
    assert comparison(offer(price=price)).conclusion == conclusion


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"gtin": "96385074"}, "identity_not_exact"),
        ({"brand": "Other"}, "identity_not_exact"),
        ({"mpn": "Other"}, "identity_not_exact"),
        ({"variant": "Decaf"}, "identity_not_exact"),
        ({"pack": None}, "unknown_pack"),
        ({"pack": {"quantity": "1", "unit": "kg", "count": 1}}, "pack_mismatch"),
        ({"pack": {"quantity": "250", "unit": "g", "count": 2}}, "pack_mismatch"),
        ({"pack": {"quantity": "500", "unit": "ml", "count": 1}}, "pack_mismatch"),
        ({"currency": "INR"}, "currency_mismatch"),
        ({"delivery_country": "GB"}, "delivery_not_confirmed"),
        ({"delivery_country": None}, "delivery_not_confirmed"),
        ({"condition": "USED"}, "condition_not_new"),
        ({"availability": "UNKNOWN"}, "stock_not_confirmed"),
        ({"availability": "OUT_OF_STOCK"}, "stock_not_confirmed"),
    ],
)
def test_cheaper_price_never_overrides_incompatibility(changes, reason):
    result = comparison(offer(price="1", **changes))
    assert not result.comparable and reason in result.reasons
    assert result.conclusion == "NOT_COMPARABLE" and result.display_price_difference is None


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"unit_price": None}, "no_historical_unit_price"),
        ({"pricing_unit": "kg"}, "unsupported_pricing_unit"),
        ({"pricing_unit": None}, "unsupported_pricing_unit"),
    ],
)
def test_unknown_baseline_never_becomes_zero(changes, reason):
    result = comparison(baseline=target(**changes))
    assert not result.comparable and reason in result.reasons


def test_uncertain_names_and_unrelated_products_preserve_matching_confidence():
    uncertain = Identity(name="Acme coffee", pack=Pack.model_validate(PACK))
    match = matching(uncertain, offer())
    assert match.status == "UNCERTAIN" and match.confidence == Decimal("0.5")
    result = comparison(baseline=target(identity=uncertain, identity_provenance="UNKNOWN"))
    assert not result.comparable
    assert matching(Identity(name="Screwdriver"), offer()).status == "MISMATCH"


def test_gtin_padding_and_brand_mpn_matching():
    assert offer().gtin == "04006381333931"
    identity = target().identity.model_copy(update={"gtin": None})
    assert matching(identity, offer(gtin=None, brand="  ACME ")).rule == "exact_brand_mpn"


def test_stale_and_future_observations_cannot_support_lower_price():
    result = compare(target(), offer(), "US", NOW, NOW)
    assert "stale_observation" in result.reasons and not result.comparable
    result = comparison(offer(observed_at=NOW + timedelta(seconds=1)))
    assert "future_observation" in result.reasons and not result.comparable


@pytest.mark.parametrize(
    "changes",
    [
        {"price": 1.2},
        {"price": True},
        {"price": "NaN"},
        {"price": "-1"},
        {"price": "1.1234567"},
        {"shipping": "-1"},
        {"tax": 1.0},
        {"currency": "ZZZ"},
        {"gtin": "4006381333932"},
        {"observed_at": "2030-09-26T06:00:00"},
        {"expires_at": NOW},
        {"source": " "},
        {"merchant": "bad\x00text"},
        {"url": "http://shop.example/item"},
        {"url": "https://127.0.0.1/item"},
        {"url": "https://secret@shop.example/item"},
        {"url": "javascript:alert(1)"},
        {"url": "https://shop.example/item\x00"},
        {"url": "https://shop.example/item\ud800"},
        {"pack": {"quantity": "500", "unit": "g"}},
        {"pack": {"quantity": "0", "unit": "g", "count": 1}},
    ],
)
def test_malformed_offer_fails_validation(changes):
    with pytest.raises(ValidationError):
        offer(**changes)


def test_strict_requests_and_duplicate_offers():
    with pytest.raises(ValidationError):
        SearchCreate(country="US")
    with pytest.raises(ValidationError):
        SearchCreate(country="US", query="arbitrary web content")
    with pytest.raises(ValidationError):
        ProviderResult(offers=[offer(), offer()])
