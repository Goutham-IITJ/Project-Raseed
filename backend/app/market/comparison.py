import re
import unicodedata
from datetime import datetime
from decimal import Decimal, localcontext

from backend.app.market.schemas import Comparison, Identity, Matching, Offer, Pack, Target


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def matching(target: Identity, offer: Identity) -> Matching:
    for field in ("gtin", "mpn", "brand", "variant"):
        left, right = getattr(target, field), getattr(offer, field)
        if left and right and normalized(left) != normalized(right):
            return Matching(status="MISMATCH", confidence=Decimal(0), rule=f"conflicting_{field}")
    if target.pack and offer.pack and pack_basis(target.pack) != pack_basis(offer.pack):
        return Matching(status="MISMATCH", confidence=Decimal(0), rule="conflicting_pack")
    if target.gtin and offer.gtin == target.gtin:
        return Matching(status="EXACT", confidence=Decimal(1), rule="exact_gtin")
    if target.brand and offer.brand and target.mpn and offer.mpn:
        return Matching(status="EXACT", confidence=Decimal(1), rule="exact_brand_mpn")
    left = set(re.findall(r"\w+", normalized(target.name)))
    right = set(re.findall(r"\w+", normalized(offer.name)))
    uncertain = bool(left & right)
    return Matching(
        status="UNCERTAIN" if uncertain else "MISMATCH",
        confidence=Decimal("0.5") if uncertain else Decimal(0),
        rule="name_overlap" if uncertain else "no_identity_match",
    )


def pack_basis(pack: Pack) -> tuple[str, Decimal, int]:
    dimension, factor = {
        "g": ("mass", 1),
        "kg": ("mass", 1000),
        "ml": ("volume", 1),
        "l": ("volume", 1000),
        "each": ("count", 1),
    }[pack.unit]
    with localcontext() as context:
        context.prec = 60
        return dimension, pack.quantity * factor, pack.count


def compare(
    target: Target,
    offer: Offer,
    country: str,
    expiry: datetime,
    now: datetime,
    *,
    match: Matching | None = None,
) -> Comparison:
    match = match or matching(target.identity, offer)
    reasons = []
    if match.status != "EXACT":
        reasons.append("identity_not_exact")
    if target.identity.pack is None or offer.pack is None:
        reasons.append("unknown_pack")
    elif pack_basis(target.identity.pack) != pack_basis(offer.pack):
        reasons.append("pack_mismatch")
    if target.unit_price is None:
        reasons.append("no_historical_unit_price")
    if normalized(target.pricing_unit or "") not in {"each", "ea", "unit", "piece", "pc"}:
        reasons.append("unsupported_pricing_unit")
    if target.currency != offer.currency:
        reasons.append("currency_mismatch")
    if offer.delivery_country != country:
        reasons.append("delivery_not_confirmed")
    if offer.condition != "NEW":
        reasons.append("condition_not_new")
    if offer.availability != "IN_STOCK":
        reasons.append("stock_not_confirmed")
    if expiry <= now:
        reasons.append("stale_observation")
    if offer.observed_at > now:
        reasons.append("future_observation")
    if reasons:
        return Comparison(
            matching=match, comparable=False, reasons=reasons, conclusion="NOT_COMPARABLE"
        )
    assert target.unit_price is not None
    with localcontext() as context:
        context.prec = 60
        difference = offer.price - target.unit_price
    return Comparison(
        matching=match,
        comparable=True,
        reasons=[],
        display_price_difference=difference,
        conclusion="LOWER_DISPLAY_PRICE"
        if difference < 0
        else "HIGHER_DISPLAY_PRICE"
        if difference > 0
        else "EQUAL_DISPLAY_PRICE",
    )
