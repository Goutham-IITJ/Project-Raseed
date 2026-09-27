from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from backend.app.purchases.schemas import InputModel, PageQuery, View

WalletStatus = Literal["PENDING", "SYNCING", "RETRY", "SYNCED", "FAILED"]


class WalletCreate(InputModel):
    purchase_id: UUID


class WalletAction(InputModel):
    pass


class WalletQuery(PageQuery):
    purchase_id: UUID | None = None
    status: WalletStatus | None = None


class WalletView(View):
    id: UUID
    purchase_id: UUID
    provider: Literal["GOOGLE"]
    pass_type: Literal["GENERIC"]
    class_id: str | None
    object_id: str | None
    status: WalletStatus
    attempt_count: int
    next_attempt_at: datetime
    last_error_code: str | None
    last_error_at: datetime | None
    synced_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WalletResponse(BaseModel):
    data: WalletView


class WalletListResponse(BaseModel):
    data: list[WalletView]


class WalletLink(BaseModel):
    save_url: str


class WalletLinkResponse(BaseModel):
    data: WalletLink
