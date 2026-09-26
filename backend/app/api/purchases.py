from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.app.api.dependencies import get_current_user, get_session, reject_query_parameters
from backend.app.config import Settings
from backend.app.identity.context import CurrentUser
from backend.app.ingestion.service import UploadService
from backend.app.ingestion.storage import ObjectStorage
from backend.app.ingestion.upload import read_upload
from backend.app.purchases.errors import DomainError
from backend.app.purchases.queries import PurchaseHistoryQuery
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


def get_upload_service(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> UploadService:
    return UploadService(
        session,
        current_user,
        cast(ObjectStorage, request.app.state.object_storage),
        cast(Settings, request.app.state.settings),
    )


@router.post(
    "/receipts",
    status_code=202,
    response_model=ReceiptResponse,
    responses={201: {"model": ReceiptResponse, "description": "Metadata-only JSON request"}},
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": ReceiptCreate.model_json_schema()},
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "additionalProperties": False,
                        "properties": {"file": {"type": "string", "format": "binary"}},
                    }
                },
            },
        }
    },
)
async def create_receipt(
    request: Request,
    response: Response,
    service: Service,
    no_query: NoQuery,
    uploader: Annotated[UploadService, Depends(get_upload_service)],
) -> ReceiptResponse:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type == "application/json":
        chunks = bytearray()
        async for chunk in request.stream():
            chunks.extend(chunk)
            if len(chunks) > 64 * 1024:
                raise DomainError
        try:
            metadata = ReceiptCreate.model_validate_json(bytes(chunks))
        except ValidationError as exc:
            raise DomainError from exc
        response.status_code = 201
        return ReceiptResponse(data=await run_in_threadpool(service.create_receipt, metadata))
    if content_type != "multipart/form-data":
        raise DomainError
    settings = cast(Settings, request.app.state.settings)
    upload = await read_upload(request, settings.max_upload_bytes)
    return ReceiptResponse(data=await run_in_threadpool(uploader.upload, upload))


@router.get("/receipts", response_model=ReceiptListResponse)
def list_receipts(service: Service, page: Pagination) -> ReceiptListResponse:
    return ReceiptListResponse(data=service.list_receipts(page))


@router.get("/receipts/{receipt_id}", response_model=ReceiptResponse)
def get_receipt(receipt_id: UUID, service: Service, no_query: NoQuery) -> ReceiptResponse:
    return ReceiptResponse(data=service.get_receipt(receipt_id))


@router.get("/purchases", response_model=PurchaseListResponse)
def list_purchases(
    service: Service, page: Annotated[PurchaseHistoryQuery, Query()]
) -> PurchaseListResponse:
    return PurchaseListResponse(data=service.list_purchases(page))


@router.get("/purchases/{purchase_id}", response_model=PurchaseResponse)
def get_purchase(purchase_id: UUID, service: Service, no_query: NoQuery) -> PurchaseResponse:
    return PurchaseResponse(data=service.get_purchase(purchase_id))
