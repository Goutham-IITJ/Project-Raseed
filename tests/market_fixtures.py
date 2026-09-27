from collections import deque

from m7_fixtures import NOW, purchase

from backend.app.market.schemas import Offer, ProviderResult, SearchCreate
from backend.app.market.service import MarketService
from backend.app.market.worker import LocalMarketTaskQueue, MarketDispatcher, MarketProcessor
from backend.app.purchases.schemas import ProductCreate
from backend.app.purchases.service import PurchaseService

PACK = {"quantity": "500", "unit": "g", "count": 1}
GTIN = "4006381333931"


def offer(**changes):
    return Offer.model_validate(
        {
            "name": "Acme coffee",
            "brand": "Acme",
            "gtin": GTIN,
            "mpn": "COFFEE-A",
            "variant": "Original",
            "pack": PACK,
            "offer_id": "offer-1",
            "source": "Fixture merchant feed",
            "merchant": "Example seller",
            "url": "https://shop.example/product/coffee",
            "location": "New York, US",
            "delivery_country": "US",
            "observed_at": NOW,
            "price": "90",
            "currency": "USD",
            "shipping": None,
            "tax": None,
            "condition": "NEW",
            "availability": "IN_STOCK",
            **changes,
        }
    )


def product_line(env, *, owner=None, metadata=None, line_changes=None):
    user = owner or env.alice
    with env.factory() as session:
        product = PurchaseService(session, user).create_product(
            ProductCreate(
                canonical_name="Acme coffee",
                brand="Acme",
                metadata=metadata
                if metadata is not None
                else {
                    "identity_source": "OBSERVED",
                    "gtin": GTIN,
                    "mpn": "COFFEE-A",
                    "variant": "Original",
                    "pack": PACK,
                },
            )
        )
    item = purchase(
        env,
        owner=user,
        amount="100",
        currency="USD",
        line_items=[
            {
                "product_id": product.id,
                "raw_name": "Coffee",
                "quantity": "1",
                "unit": "each",
                "unit_price": "100",
                "line_total": "100",
                **(line_changes or {}),
            }
        ],
    )
    return product, item, item.line_items[0]


def search(env, line, *, user=None, now=NOW, **changes):
    with env.factory() as session:
        return MarketService(session, user or env.alice, clock=lambda: now).search(
            SearchCreate(line_item_id=line.id, country="US", **changes)
        )


def read(env, search_id, *, now=NOW, user=None):
    with env.factory() as session:
        return MarketService(session, user or env.alice, clock=lambda: now).get(search_id)


class FakeMarket:
    name = "TEST_MARKET"

    def __init__(self, *results):
        self.results = deque(results)
        self.calls = []
        self.before_search = None

    def search(self, query):
        self.calls.append(query)
        if self.before_search:
            self.before_search()
        result = self.results.popleft() if self.results else ProviderResult(offers=[offer()])
        if isinstance(result, Exception):
            raise result
        return result


def worker(env, provider=None, *, clock=lambda: NOW):
    fake = provider or FakeMarket()
    processor = MarketProcessor(env.factory, fake, clock=clock)
    return (
        processor,
        MarketDispatcher(env.factory, LocalMarketTaskQueue(processor), clock=clock),
        fake,
    )
