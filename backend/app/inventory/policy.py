import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

EligibilitySource = Literal["PRODUCT", "CATEGORY", "UNKNOWN"]


def normalize_unit(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


@dataclass(frozen=True)
class Eligibility:
    eligible: bool
    reason: Literal[
        "ELIGIBLE", "EXCLUDED", "UNKNOWN_ELIGIBILITY", "MISSING_QUANTITY", "MISSING_UNIT"
    ]
    source: EligibilitySource


def inventory_eligibility(
    flag: bool | None,
    source: EligibilitySource,
    quantity: Decimal | None,
    unit: str | None,
) -> Eligibility:
    if flag is None:
        return Eligibility(False, "UNKNOWN_ELIGIBILITY", source)
    if not flag:
        return Eligibility(False, "EXCLUDED", source)
    if quantity is None:
        return Eligibility(False, "MISSING_QUANTITY", source)
    # Normalization may expand text; never truncate it to force an identity match.
    if not unit or not normalize_unit(unit) or len(normalize_unit(unit)) > 40:
        return Eligibility(False, "MISSING_UNIT", source)
    return Eligibility(True, "ELIGIBLE", source)
