import json
import math
import re
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Any, Literal
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.market.provider import MarketFailure
from backend.app.market.schemas import MarketQuery, Offer, Pack, ProviderResult
from backend.app.purchases.queries import utc_now

BASE_URL = "https://api.ebay.com/buy/browse/v1/"
MARKETPLACES = {"EBAY_US": "US", "EBAY_GB": "GB", "EBAY_DE": "DE", "EBAY_AU": "AU"}


def retry_delay(value: str | None, now: datetime) -> int:
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


class EbayMarketProvider:
    name = "EBAY"

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.settings, self.transport, self.clock = settings, transport, clock

    def _get(
        self, client: httpx.Client, path: str, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        try:
            with client.stream("GET", BASE_URL + path, params=params) as response:
                status = response.status_code
                if status in (401, 403):
                    raise MarketFailure("market_authorization")
                if status == 429 or status == 408 or status >= 500:
                    raise MarketFailure(
                        "market_rate_limited" if status == 429 else "market_unavailable",
                        retryable=True,
                        retry_after=retry_delay(response.headers.get("Retry-After"), self.clock()),
                    )
                if status != 200:
                    raise MarketFailure("market_rejected")
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > 131072:
                        raise MarketFailure("market_invalid_data")
            body = json.loads(content, parse_float=Decimal)
            if not isinstance(body, dict):
                raise MarketFailure("market_invalid_data")
            return {str(key): value for key, value in body.items()}
        except httpx.TimeoutException as exc:
            raise MarketFailure("market_timeout", retryable=True) from exc
        except httpx.RequestError as exc:
            raise MarketFailure("market_unavailable", retryable=True) from exc
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise MarketFailure("market_invalid_data") from exc

    def search(self, query: MarketQuery) -> ProviderResult:
        token = self.settings.market_ebay_token.get_secret_value()
        marketplace = self.settings.market_ebay_marketplace
        if not token or MARKETPLACES[marketplace] != query.country:
            raise MarketFailure("market_configuration")
        context = "country=" + query.country
        if query.postal_code:
            context += ",zip=" + query.postal_code
        headers = {
            "Authorization": "Bearer " + token,
            "X-EBAY-C-MARKETPLACE-ID": marketplace,
            "X-EBAY-C-ENDUSERCTX": "contextualLocation=" + quote(context, safe=""),
        }
        params = {"limit": "5", "filter": "conditionIds:{1000},buyingOptions:{FIXED_PRICE}"}
        params.update(
            {"gtin": query.identity.gtin} if query.identity.gtin else {"q": query.identity.name}
        )
        try:
            with httpx.Client(
                transport=self.transport,
                timeout=self.settings.market_request_timeout_seconds,
                headers=headers,
                follow_redirects=False,
            ) as client:
                response = self._get(client, "item_summary/search", params)
                summaries = response.get("itemSummaries")
                if (
                    summaries is None
                    and type(response.get("total")) is int
                    and response["total"] == 0
                ):
                    return ProviderResult(offers=[])
                if not isinstance(summaries, list) or len(summaries) > 5:
                    raise MarketFailure("market_invalid_data")
                offers = []
                for summary in summaries:
                    item_id = summary["itemId"]
                    if not isinstance(item_id, str) or not re.fullmatch(
                        r"v1\|[0-9]+\|[0-9]+", item_id
                    ):
                        raise MarketFailure("market_invalid_data")
                    # Never follow provider-supplied itemHref/product URLs.
                    detail = self._get(client, "item/" + quote(item_id, safe=""))
                    if detail.get("itemId") != item_id:
                        raise MarketFailure("market_invalid_data")
                    offers.append(self._offer(detail))
                return ProviderResult(offers=offers)
        except (KeyError, TypeError, ValueError, ValidationError, AttributeError) as exc:
            raise MarketFailure("market_invalid_data") from exc

    def _offer(self, item: dict[str, Any]) -> Offer:
        aspects: dict[str, Any] = {}
        for entry in item.get("localizedAspects", []):
            key = entry["name"].casefold()
            if key in aspects:
                raise ValueError("Ambiguous structured aspect")
            aspects[key] = entry["value"]
        pack = None
        # Only explicit structured pack data; do not parse arbitrary listing titles.
        if item.get("lotSize", 1) == 1 and all(
            key in aspects for key in ("unit quantity", "unit type", "number in pack")
        ):
            unit = aspects["unit type"].strip().casefold()
            units = {"g": "g", "gram": "g", "kg": "kg", "ml": "ml", "l": "l", "unit": "each"}
            count = aspects["number in pack"]
            if unit in units and isinstance(count, str) and re.fullmatch(r"[1-9][0-9]{0,3}", count):
                pack = Pack.model_validate(
                    {"quantity": aspects["unit quantity"], "unit": units[unit], "count": int(count)}
                )
        shipping, destination = None, None
        options = item.get("shippingOptions", [])
        if len(options) == 1:
            option = options[0]
            destination = option.get("shipToLocationUsedForEstimate", {}).get("country")
            cost = option.get("shippingCost")
            if cost is not None and cost["currency"] == item["price"]["currency"]:
                shipping = cost["value"]
        locations = item.get("itemLocation", {})
        location = (
            ", ".join(
                locations[key]
                for key in ("city", "stateOrProvince", "postalCode", "country")
                if locations.get(key)
            )
            or None
        )
        availability = {
            entry.get("estimatedAvailabilityStatus")
            for entry in item.get("estimatedAvailabilities", [])
        }
        stock: Literal["IN_STOCK", "OUT_OF_STOCK", "UNKNOWN"] = (
            "IN_STOCK"
            if availability and availability <= {"IN_STOCK", "LIMITED_STOCK"}
            else "OUT_OF_STOCK"
            if availability == {"OUT_OF_STOCK"}
            else "UNKNOWN"
        )
        return Offer(
            name=item["title"],
            brand=item.get("brand"),
            gtin=item.get("gtin"),
            mpn=item.get("mpn"),
            variant=aspects.get("model"),
            pack=pack,
            offer_id=item["itemId"],
            source="eBay Browse",
            merchant=item["seller"]["username"],
            url=item["itemWebUrl"],
            location=location,
            delivery_country=destination,
            observed_at=self.clock(),
            price=item["price"]["value"],
            currency=item["price"]["currency"],
            shipping=shipping,
            tax=None,
            condition="NEW"
            if item.get("conditionId") == "1000"
            else "USED"
            if item.get("conditionId")
            else "UNKNOWN",
            availability=stock,
        )
