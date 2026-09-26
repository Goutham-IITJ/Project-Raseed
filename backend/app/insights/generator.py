"""Explanation boundary: the default is deterministic and needs no AI provider."""

from typing import Protocol

from pydantic import JsonValue

from backend.app.insights.schemas import ExpirySource, InsightType, SpendingSource, UnusualSource


class InsightGenerator(Protocol):
    def explain(self, kind: InsightType, source: dict[str, JsonValue]) -> tuple[str, str]: ...


class DeterministicInsightGenerator:
    def explain(self, kind: InsightType, source: dict[str, JsonValue]) -> tuple[str, str]:
        if kind == "SPENDING_CHANGE":
            spending = SpendingSource.model_validate(source)
            metrics = spending.metrics
            return "Recorded spending changed", (
                f"Recorded spending for {spending.period.start_date} to "
                f"{spending.period.end_date} (exclusive) was {metrics.current_total} "
                f"{metrics.currency}, compared with {metrics.comparison_total} "
                f"{metrics.currency} in the preceding month. "
                f"Change: {metrics.percentage_change}%."
            )
        if kind == "UNUSUAL_PURCHASE":
            unusual = UnusualSource.model_validate(source)
            return "A large recorded purchase", (
                f"The largest purchase on {unusual.period.start_date} was "
                f"{unusual.current.largest_purchase} {unusual.current.currency}. "
                f"It was at least three times the mean of the preceding thirty days' "
                f"{unusual.baseline.purchase_count} recorded purchases in that currency "
                f"(mean {unusual.baseline.average_purchase}). This is a threshold "
                "observation, not evidence of fraud or recurring spending."
            )
        expiry = ExpirySource.model_validate(source)
        return "Recorded inventory expiry", (
            f"{expiry.lot.name} has {expiry.lot.quantity_remaining} {expiry.lot.unit} remaining "
            f"as of {expiry.as_of_date}, with recorded expiry {expiry.lot.expiry.date} "
            f"({expiry.lot.expiry.source}, {expiry.lot.expiry.provenance}). "
            "The recorded date is due within three days or has passed; "
            "it is not a food-safety assessment."
        )
