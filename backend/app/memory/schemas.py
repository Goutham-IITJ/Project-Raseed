from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from backend.app.assistant.schemas import valid_text
from backend.app.purchases.schemas import InputModel, PageQuery, View, aware_utc

MemoryType = Literal["PREFERENCE", "GOAL", "HABIT", "CONSTRAINT", "FACT"]
Topic = Literal["food", "spending", "inventory", "shopping", "goals"]


class MemoryCreate(InputModel):
    type: MemoryType
    content: Annotated[str, Field(min_length=1, max_length=1000)]
    topics: Annotated[list[Topic], Field(max_length=5)] = Field(default_factory=list)
    expires_at: datetime | None = None
    source_message_id: UUID | None = None

    _content = field_validator("content")(valid_text)

    @field_validator("topics")
    @classmethod
    def unique_topics(cls, value: list[Topic]) -> list[Topic]:
        if len(set(value)) != len(value):
            raise ValueError("Repeated memory topic")
        return sorted(value)

    @field_validator("expires_at")
    @classmethod
    def expiry(cls, value: datetime | None) -> datetime | None:
        return aware_utc(value) if value is not None else None


class MemoryVersion(InputModel):
    expected_version: Annotated[int, Field(ge=1)]


class MemoryUpdate(MemoryCreate, MemoryVersion):
    expected_version: Annotated[int, Field(ge=1, strict=True)]


class MemoryQuery(PageQuery):
    query: Annotated[str, Field(min_length=1, max_length=1000)] | None = None
    type: MemoryType | None = None
    include_expired: bool = False

    @field_validator("query")
    @classmethod
    def search_text(cls, value: str | None) -> str | None:
        return valid_text(value) if value is not None else None


class MemoryView(View):
    id: UUID
    type: MemoryType
    content: str
    topics: list[Topic]
    source: Literal["USER_EXPLICIT"]
    provenance: Literal["OBSERVED"]
    confidence: Decimal
    source_message_id: UUID | None
    expires_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class MemoryResponse(View):
    data: MemoryView


class MemoryListResponse(View):
    data: list[MemoryView]
