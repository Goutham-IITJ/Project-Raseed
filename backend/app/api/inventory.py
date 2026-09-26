from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user, get_session, reject_query_parameters
from backend.app.identity.context import CurrentUser
from backend.app.inventory.schemas import (
    CandidateListResponse,
    EventCreate,
    EventListResponse,
    EventResponse,
    ItemListResponse,
    ItemResponse,
    LotCreate,
    LotListResponse,
    LotResponse,
)
from backend.app.inventory.service import InventoryService
from backend.app.purchases.schemas import PageQuery

router = APIRouter(prefix="/api/v1", tags=["Inventory"])


def get_inventory_service(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> InventoryService:
    return InventoryService(session, current_user)


Service = Annotated[InventoryService, Depends(get_inventory_service)]
NoQuery = Annotated[None, Depends(reject_query_parameters)]
Pagination = Annotated[PageQuery, Query()]


@router.get("/inventory/items", response_model=ItemListResponse)
def list_items(service: Service, page: Pagination) -> ItemListResponse:
    return ItemListResponse(data=service.list_items(page))


@router.get("/inventory/items/{item_id}", response_model=ItemResponse)
def get_item(item_id: UUID, service: Service, no_query: NoQuery) -> ItemResponse:
    return ItemResponse(data=service.get_item(item_id))


@router.get("/inventory/items/{item_id}/lots", response_model=LotListResponse)
def item_lots(item_id: UUID, service: Service, page: Pagination) -> LotListResponse:
    return LotListResponse(data=service.list_lots(page, item_id))


@router.get("/inventory/lots", response_model=LotListResponse)
def list_lots(service: Service, page: Pagination) -> LotListResponse:
    return LotListResponse(data=service.list_lots(page))


@router.get("/inventory/lots/{lot_id}", response_model=LotResponse)
def get_lot(lot_id: UUID, service: Service, no_query: NoQuery) -> LotResponse:
    return LotResponse(data=service.get_lot(lot_id))


@router.post("/inventory/lots", status_code=201, response_model=LotResponse)
def create_lot(data: LotCreate, service: Service, no_query: NoQuery) -> LotResponse:
    return LotResponse(data=service.create_lot(data))


@router.get("/inventory/lots/{lot_id}/events", response_model=EventListResponse)
def list_events(lot_id: UUID, service: Service, page: Pagination) -> EventListResponse:
    return EventListResponse(data=service.list_events(lot_id, page))


@router.post("/inventory/lots/{lot_id}/events", status_code=201, response_model=EventResponse)
def create_event(
    lot_id: UUID, data: EventCreate, service: Service, no_query: NoQuery
) -> EventResponse:
    return EventResponse(data=service.record_event(lot_id, data))


@router.get("/purchases/{purchase_id}/inventory-candidates", response_model=CandidateListResponse)
def candidates(purchase_id: UUID, service: Service, no_query: NoQuery) -> CandidateListResponse:
    return CandidateListResponse(data=service.candidates(purchase_id))
