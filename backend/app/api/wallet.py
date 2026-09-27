from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user, get_session, reject_query_parameters
from backend.app.identity.context import CurrentUser
from backend.app.wallet.provider import WalletProvider
from backend.app.wallet.schemas import (
    WalletAction,
    WalletCreate,
    WalletLinkResponse,
    WalletListResponse,
    WalletQuery,
    WalletResponse,
)
from backend.app.wallet.service import WalletService

router = APIRouter(prefix="/api/v1/wallet/passes", tags=["Wallet"])


def get_wallet_service(
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> WalletService:
    return WalletService(session, user, cast(WalletProvider, request.app.state.wallet_provider))


Service = Annotated[WalletService, Depends(get_wallet_service)]
NoQuery = Annotated[None, Depends(reject_query_parameters)]


@router.post("", response_model=WalletResponse, status_code=202)
def create_pass(data: WalletCreate, service: Service, no_query: NoQuery) -> WalletResponse:
    return WalletResponse(data=service.create(data))


@router.get("", response_model=WalletListResponse)
def list_passes(service: Service, query: Annotated[WalletQuery, Query()]) -> WalletListResponse:
    return WalletListResponse(data=service.list(query))


@router.get("/{pass_id}", response_model=WalletResponse)
def get_pass(pass_id: UUID, service: Service, no_query: NoQuery) -> WalletResponse:
    return WalletResponse(data=service.get(pass_id))


@router.post("/{pass_id}/sync", response_model=WalletResponse, status_code=202)
def sync_pass(
    pass_id: UUID, data: WalletAction, service: Service, no_query: NoQuery
) -> WalletResponse:
    return WalletResponse(data=service.sync(pass_id))


@router.post("/{pass_id}/add-to-wallet", response_model=WalletLinkResponse)
def add_to_wallet(
    pass_id: UUID, data: WalletAction, service: Service, no_query: NoQuery
) -> WalletLinkResponse:
    return WalletLinkResponse(data=service.add_to_wallet(pass_id))
