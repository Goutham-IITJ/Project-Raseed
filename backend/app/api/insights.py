from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user, get_session, reject_query_parameters
from backend.app.identity.context import CurrentUser
from backend.app.insights.schemas import (
    InsightListResponse,
    InsightQuery,
    InsightResponse,
    InsightUpdate,
)
from backend.app.insights.service import InsightService

router = APIRouter(prefix="/api/v1/insights", tags=["Insights"])


def get_insight_service(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> InsightService:
    return InsightService(session, user)


Service = Annotated[InsightService, Depends(get_insight_service)]
NoQuery = Annotated[None, Depends(reject_query_parameters)]


@router.get("", response_model=InsightListResponse)
def list_insights(service: Service, query: Annotated[InsightQuery, Query()]) -> InsightListResponse:
    return InsightListResponse(data=service.list(query))


@router.get("/{insight_id}", response_model=InsightResponse)
def get_insight(insight_id: UUID, service: Service, no_query: NoQuery) -> InsightResponse:
    return InsightResponse(data=service.get(insight_id))


@router.patch("/{insight_id}", response_model=InsightResponse)
def update_insight(
    insight_id: UUID, data: InsightUpdate, service: Service, no_query: NoQuery
) -> InsightResponse:
    return InsightResponse(data=service.update(insight_id, data))
