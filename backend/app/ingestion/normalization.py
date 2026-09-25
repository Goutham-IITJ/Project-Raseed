"""Catalog persistence under the caller's canonical transaction."""

import unicodedata
from uuid import UUID

from sqlalchemy import select, text

from backend.app.ingestion.schema import ProductEvidence, ReceiptExtractionV1
from backend.app.purchases.models import Category, Merchant, Product
from backend.app.purchases.repositories import CatalogRepository
from backend.app.purchases.schemas import MerchantCreate, ProductCreate, PurchaseCreate


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def valid_gtin(value: str) -> bool:
    return (
        len(value) in {8, 12, 13, 14}
        and value.isascii()
        and value.isdigit()
        and sum(
            int(digit) * (1 if index % 2 == 0 else 3) for index, digit in enumerate(reversed(value))
        )
        % 10
        == 0
    )


class NormalizationRepository(CatalogRepository):
    def _serialize_identity(self, identity: str) -> None:
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
            {"identity": identity},
        )

    def merchant(self, name: str, address: str | None) -> UUID:
        key = normalized(name)
        location = normalized(address) if address else None
        self._serialize_identity(f"merchant:{key}:{location}")
        matches = list(
            self._session.scalars(select(Merchant).where(Merchant.normalized_name == key))
        )
        exact = [
            merchant
            for merchant in matches
            if (normalized(merchant.address) if merchant.address else None) == location
        ]
        if len(exact) == 1:
            return exact[0].id
        return self.create_merchant(MerchantCreate(canonical_name=name, address=address)).id

    def category(self, suggestion: str | None) -> UUID | None:
        if not suggestion:
            return None
        key = normalized(suggestion)
        # The catalog is deliberately unseeded. Match existing exact identities only.
        matches = [
            category
            for category in self._session.scalars(select(Category))
            if category.slug == key or normalized(category.name) == key
        ]
        return matches[0].id if len(matches) == 1 else None

    def product(self, evidence: ProductEvidence | None, category_id: UUID | None) -> UUID | None:
        if (
            evidence is None
            or evidence.source != "OBSERVED"
            or evidence.gtin is None
            or not valid_gtin(evidence.gtin)
            or not evidence.name
            or evidence.confidence is None
            or evidence.confidence < 0.9
        ):
            return None
        self._serialize_identity(f"product:{evidence.gtin}")
        matches = list(
            self._session.scalars(
                select(Product).where(Product.product_metadata["gtin"].astext == evidence.gtin)
            )
        )
        if len(matches) == 1:
            return matches[0].id
        if matches:
            return None
        return self.create_product(
            ProductCreate(
                canonical_name=evidence.name,
                brand=evidence.brand,
                category_id=category_id,
                metadata={"gtin": evidence.gtin, "identity_source": "OBSERVED"},
            )
        ).id

    def normalize(self, command: PurchaseCreate, data: ReceiptExtractionV1) -> PurchaseCreate:
        command.merchant_id = self.merchant(command.merchant_name_raw, data.merchant_address)
        command.category_id = self.category(data.category_suggestion)
        for item, evidence in zip(command.line_items, data.line_items, strict=True):
            item.normalized_name = normalized(item.raw_name)
            item.category_id = self.category(evidence.category_suggestion)
            item.product_id = self.product(evidence.product, item.category_id)
        return PurchaseCreate.model_validate(command.model_dump())
