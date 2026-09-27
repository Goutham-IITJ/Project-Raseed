from pydantic import ValidationError

from backend.app.market.schemas import Identity, Target
from backend.app.purchases.models import LineItem, Product, Purchase


def identify(
    product: Product | None, line: LineItem | None, purchase: Purchase | None, currency: str
) -> Target:
    metadata = product.product_metadata or {} if product else {}
    observed = metadata.get("identity_source") == "OBSERVED"
    identity = Identity(
        name=product.canonical_name if product else line.raw_name if line else "Unknown"
    )
    if product is not None and observed:
        for field, value in {
            "brand": product.brand,
            "gtin": metadata.get("gtin"),
            "mpn": metadata.get("mpn"),
            "variant": metadata.get("variant"),
            "pack": metadata.get("pack"),
        }.items():
            try:
                identity = Identity.model_validate({**identity.model_dump(), field: value})
            except ValidationError:
                pass  # Invalid optional catalog evidence stays unknown, never an exact match.
    return Target(
        identity=identity,
        identity_provenance="OBSERVED" if observed else "UNKNOWN",
        currency=purchase.currency if purchase else currency,
        unit_price=line.unit_price if line else None,
        pricing_unit=line.unit if line else None,
        purchased_at=purchase.purchased_at if purchase else None,
    )
