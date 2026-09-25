from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user, get_session, reject_query_parameters
from backend.app.identity.context import CurrentUser
from backend.app.purchases.schemas import (
    PageQuery,
    PurchaseListResponse,
    PurchaseResponse,
    ReceiptCreate,
    ReceiptListResponse,
    ReceiptResponse,
)
from backend.app.purchases.service import PurchaseService

router = APIRouter(prefix="/api/v1", tags=["Receipt and purchase foundation"])


def get_purchase_service(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> PurchaseService:
    return PurchaseService(session, current_user)


Service = Annotated[PurchaseService, Depends(get_purchase_service)]
NoQuery = Annotated[None, Depends(reject_query_parameters)]
Pagination = Annotated[PageQuery, Query()]


@router.post("/receipts", status_code=201, response_model=ReceiptResponse)
def create_receipt(body: ReceiptCreate, service: Service, no_query: NoQuery) -> ReceiptResponse:
    return ReceiptResponse(data=service.create_receipt(body))


@router.get("/receipts", response_model=ReceiptListResponse)
def list_receipts(service: Service, page: Pagination) -> ReceiptListResponse:
    return ReceiptListResponse(data=service.list_receipts(page))


@router.get("/receipts/{receipt_id}", response_model=ReceiptResponse)
def get_receipt(receipt_id: UUID, service: Service, no_query: NoQuery) -> ReceiptResponse:
    return ReceiptResponse(data=service.get_receipt(receipt_id))


@router.get("/purchases", response_model=PurchaseListResponse)
def list_purchases(service: Service, page: Pagination) -> PurchaseListResponse:
    return PurchaseListResponse(data=service.list_purchases(page))


@router.get("/purchases/{purchase_id}", response_model=PurchaseResponse)
def get_purchase(purchase_id: UUID, service: Service, no_query: NoQuery) -> PurchaseResponse:
    return PurchaseResponse(data=service.get_purchase(purchase_id))
