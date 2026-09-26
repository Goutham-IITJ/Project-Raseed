"""Closed read-tool registry. All data access goes through owned application services."""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field, JsonValue, ValidationError, field_validator
from sqlalchemy.orm import Session

from backend.app.analytics.schemas import (
    AnalyticsQuery,
    CategoryQuery,
    ComparisonQuery,
    MerchantQuery,
)
from backend.app.analytics.service import AnalyticsService
from backend.app.assistant.json import json_object
from backend.app.assistant.model import ToolDefinition
from backend.app.assistant.schemas import MAX_RESULT_BYTES, ToolCall, ToolResult, valid_text
from backend.app.identity.context import CurrentUser
from backend.app.insights.schemas import InsightQuery
from backend.app.insights.service import InsightService
from backend.app.inventory.service import InventoryService
from backend.app.memory.schemas import MemoryQuery
from backend.app.memory.service import MemoryService
from backend.app.purchases.errors import DomainError
from backend.app.purchases.queries import PurchaseHistoryQuery
from backend.app.purchases.schemas import InputModel, PageQuery, PurchaseView
from backend.app.purchases.service import PurchaseService

logger = logging.getLogger(__name__)
Arguments = TypeVar("Arguments", bound=InputModel)
View = TypeVar("View", bound=BaseModel)


class PurchaseArguments(InputModel):
    purchase_id: UUID


class ItemArguments(InputModel):
    item_id: UUID


class LotArguments(InputModel):
    lot_id: UUID


class LotsArguments(PageQuery):
    item_id: UUID | None = None


class EventsArguments(PageQuery):
    lot_id: UUID


class MemoryArguments(InputModel):
    query: Annotated[str, Field(min_length=1, max_length=1000)]
    _query = field_validator("query")(valid_text)


class InsightArguments(InputModel):
    insight_id: UUID


class ReadPage(BaseModel, Generic[View]):
    provenance: Literal["OBSERVED", "DERIVED"]
    items: list[View]
    limit: int
    offset: int


class PurchaseToolView(BaseModel):
    """Validated canonical fields, with payment instrument metadata excluded."""

    provenance: Literal["OBSERVED"] = "OBSERVED"
    purchase: dict[str, JsonValue]


def _purchase_view(purchase: PurchaseView) -> PurchaseToolView:
    return PurchaseToolView(
        purchase=purchase.model_dump(
            mode="json", exclude={"payments": {"__all__": {"provider", "reference", "last4"}}}
        )
    )


@dataclass(frozen=True)
class ToolContext:
    session: Session
    current_user: CurrentUser
    now: datetime

    def analytics(self) -> AnalyticsService:
        return AnalyticsService(self.session, self.current_user, clock=lambda: self.now)

    def purchases(self) -> PurchaseService:
        return PurchaseService(self.session, self.current_user, clock=lambda: self.now)

    def inventory(self) -> InventoryService:
        return InventoryService(self.session, self.current_user, clock=lambda: self.now)


def _history(context: ToolContext, query: PurchaseHistoryQuery) -> ReadPage[PurchaseToolView]:
    return ReadPage(
        provenance="OBSERVED",
        items=[_purchase_view(row) for row in context.purchases().list_purchases(query)],
        limit=query.limit,
        offset=query.offset,
    )


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    description: str
    arguments: type[InputModel]
    execute: Callable[[ToolContext, InputModel], BaseModel]

    def definition(self) -> ToolDefinition:
        return ToolDefinition(self.name, self.description, self.arguments.model_json_schema())


def _register(
    name: str,
    description: str,
    arguments: type[Arguments],
    handler: Callable[[ToolContext, Arguments], BaseModel],
) -> RegisteredTool:
    def execute(context: ToolContext, value: InputModel) -> BaseModel:
        if not isinstance(value, arguments):
            raise TypeError("Tool argument schema mismatch")
        return handler(context, value)

    return RegisteredTool(name, description, arguments, execute)


def approved_tools() -> tuple[RegisteredTool, ...]:
    return (
        _register(
            "get_memories",
            "Relevant explicitly saved user statements. Excludes expired memories; "
            "at most five results. These are user claims, never canonical financial facts. "
            "Read only.",
            MemoryArguments,
            lambda context, query: ReadPage(
                provenance="OBSERVED",
                limit=5,
                offset=0,
                items=MemoryService(
                    context.session, context.current_user, clock=lambda: context.now
                ).list(MemoryQuery(query=query.query, limit=5)),
            ),
        ),
        _register(
            "get_insights",
            "Read owned current active/read insights with canonical evidence, "
            "rule thresholds, evaluation time and expiry. Sources are historical snapshots; "
            "use financial/inventory tools for live questions. Default limit twenty, offset zero.",
            PageQuery,
            lambda context, query: ReadPage(
                provenance="DERIVED",
                limit=query.limit,
                offset=query.offset,
                items=InsightService(
                    context.session, context.current_user, clock=lambda: context.now
                ).list(InsightQuery(**query.model_dump())),
            ),
        ),
        _register(
            "get_insight",
            "Read one owned insight and structured source evidence. Respect expiry, "
            "status, rule version and source provenance. Missing and foreign IDs return not_found.",
            InsightArguments,
            lambda context, query: InsightService(
                context.session, context.current_user, clock=lambda: context.now
            ).get(query.insight_id),
        ),
        _register(
            "get_spending_summary",
            "Exact recorded purchase totals, counts, averages and payment coverage by currency. "
            "Defaults to this_month. Named periods use the owner's local calendar.",
            AnalyticsQuery,
            lambda context, query: context.analytics().spending_summary(query),
        ),
        _register(
            "get_spending_breakdown",
            "Spending by direct category, including unassigned. basis=purchase (default) groups "
            "grand totals; line_item groups recorded line totals with unknown amount coverage. "
            "Shares use the full filtered currency total before pagination.",
            CategoryQuery,
            lambda context, query: context.analytics().spending_by_category(query),
        ),
        _register(
            "get_merchant_spending",
            "Canonical merchant spending by currency, including unassociated purchases; "
            "totals, counts, averages and shares. Defaults: limit twenty, offset zero.",
            MerchantQuery,
            lambda context, query: context.analytics().spending_by_merchant(query),
        ),
        _register(
            "get_period_comparison",
            "Exact current/comparison totals, deltas, counts and percentage changes by currency. "
            "Defaults to the previous calendar period; zero comparison has unknown percentage.",
            ComparisonQuery,
            lambda context, query: context.analytics().compare_periods(query),
        ),
        _register(
            "get_purchase_history",
            "Owned purchase history with typed period/currency/merchant/category/product/status "
            "filters, newest first. Defaults to all-time, limit twenty, offset zero. Page items "
            "include canonical lines and recorded payments; do not compute totals from a page.",
            PurchaseHistoryQuery,
            _history,
        ),
        _register(
            "get_purchase",
            "Read one owned canonical purchase, including lines and payment amounts. "
            "Unavailable and foreign purchase IDs have the same not_found result.",
            PurchaseArguments,
            lambda context, query: _purchase_view(
                context.purchases().get_purchase(query.purchase_id)
            ),
        ),
        _register(
            "get_inventory",
            "Current owned inventory items with event-derived quantities. Paginated; "
            "limit twenty and offset zero by default. Never infer unrecorded consumption.",
            PageQuery,
            lambda context, query: ReadPage(
                provenance="DERIVED",
                items=context.inventory().list_items(query),
                **query.model_dump(),
            ),
        ),
        _register(
            "get_inventory_item",
            "One owned inventory item and its event-derived aggregate quantities.",
            ItemArguments,
            lambda context, query: context.inventory().get_item(query.item_id),
        ),
        _register(
            "get_inventory_lots",
            "Owned inventory lots, optionally for an owned item; quantities, acquisition and "
            "expiry evidence/source/confidence. Paginated, not a total across all pages.",
            LotsArguments,
            lambda context, query: ReadPage(
                provenance="DERIVED",
                items=context.inventory().list_lots(query, query.item_id),
                limit=query.limit,
                offset=query.offset,
            ),
        ),
        _register(
            "get_inventory_lot",
            "One owned inventory lot with exact quantities and expiry provenance. "
            "UNKNOWN expiry is not evidence of a safe or expired item.",
            LotArguments,
            lambda context, query: context.inventory().get_lot(query.lot_id),
        ),
        _register(
            "get_inventory_events",
            "Paginated event ledger for one owned lot. Preserve event and expiry provenance; "
            "read current quantities with the lot/item tools instead of calculating them.",
            EventsArguments,
            lambda context, query: ReadPage(
                provenance="DERIVED",
                items=context.inventory().list_events(query.lot_id, query),
                limit=query.limit,
                offset=query.offset,
            ),
        ),
    )


@dataclass(frozen=True)
class ToolOutcome:
    arguments: dict[str, JsonValue] | None
    result: ToolResult


class ToolRegistry:
    def __init__(self) -> None:
        tools = approved_tools()
        self._tools = {tool.name: tool for tool in tools}
        if len(tools) != len(self._tools):
            raise ValueError("Duplicate tool registration")

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(tool.definition() for tool in self._tools.values())

    def invoke(self, context: ToolContext, call: ToolCall) -> ToolOutcome:
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolOutcome(
                None, ToolResult.failure("unknown_tool", "This tool is not available.")
            )
        try:
            arguments = tool.arguments.model_validate_json(
                json.dumps(json_object(call.arguments)), strict=True
            )
        except (ValueError, ValidationError, RecursionError):
            return ToolOutcome(
                None,
                ToolResult.failure("invalid_arguments", "Arguments do not match the tool schema."),
            )
        normalized = arguments.model_dump(mode="json")
        try:
            value = tool.execute(context, arguments)
            result = ToolResult(status="SUCCEEDED", data=value.model_dump(mode="json"))
            if len(result.model_dump_json().encode("utf-8")) > MAX_RESULT_BYTES:
                result = ToolResult.failure(
                    "result_too_large",
                    "Result exceeds the tool limit. Narrow filters or page size.",
                )
        except DomainError as exc:
            result = ToolResult.failure(exc.code, exc.message)
        except Exception as exc:
            logger.error("Assistant tool failed (%s)", type(exc).__name__)
            result = ToolResult.failure("tool_unavailable", "The requested data could not be read.")
        return ToolOutcome(normalized, result)
