from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user, get_session, reject_query_parameters
from backend.app.identity.context import CurrentUser
from backend.app.market.schemas import (
    ObservationResponse,
    RetrySearch,
    SearchCreate,
    SearchResponse,
)
from backend.app.market.service import MarketService

router = APIRouter(prefix="/api/v1/market", tags=["Market intelligence"])


def get_market_service(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> MarketService:
    return MarketService(session, user)


Service = Annotated[MarketService, Depends(get_market_service)]
NoQuery = Annotated[None, Depends(reject_query_parameters)]


@router.post("/searches", response_model=SearchResponse, status_code=202)
def search(data: SearchCreate, service: Service, no_query: NoQuery) -> SearchResponse:
    return SearchResponse(data=service.search(data))


@router.get("/searches/{search_id}", response_model=SearchResponse)
def get_search(search_id: UUID, service: Service, no_query: NoQuery) -> SearchResponse:
    return SearchResponse(data=service.get(search_id))


@router.post("/searches/{search_id}/retry", response_model=SearchResponse, status_code=202)
def retry(
    search_id: UUID, data: RetrySearch, service: Service, no_query: NoQuery
) -> SearchResponse:
    return SearchResponse(data=service.retry(search_id))


@router.get("/observations/{observation_id}", response_model=ObservationResponse)
def observation(observation_id: UUID, service: Service, no_query: NoQuery) -> ObservationResponse:
    return ObservationResponse(data=service.observation(observation_id))
