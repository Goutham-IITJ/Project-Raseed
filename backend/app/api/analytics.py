from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.analytics.schemas import (
    AnalyticsQuery,
    CategoryQuery,
    CategoryResponse,
    ComparisonQuery,
    ComparisonResponse,
    MerchantQuery,
    MerchantResponse,
    SummaryResponse,
)
from backend.app.analytics.service import AnalyticsService
from backend.app.api.dependencies import get_current_user, get_session
from backend.app.identity.context import CurrentUser

router = APIRouter(prefix="/api/v1/analytics", tags=["Financial analytics"])


def get_analytics_service(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> AnalyticsService:
    return AnalyticsService(session, current_user)


Service = Annotated[AnalyticsService, Depends(get_analytics_service)]


@router.get("/spending-summary", response_model=SummaryResponse)
def spending_summary(
    service: Service, query: Annotated[AnalyticsQuery, Query()]
) -> SummaryResponse:
    return SummaryResponse(data=service.spending_summary(query))


@router.get("/spending-by-category", response_model=CategoryResponse)
def spending_by_category(
    service: Service, query: Annotated[CategoryQuery, Query()]
) -> CategoryResponse:
    return CategoryResponse(data=service.spending_by_category(query))


@router.get("/spending-by-merchant", response_model=MerchantResponse)
def spending_by_merchant(
    service: Service, query: Annotated[MerchantQuery, Query()]
) -> MerchantResponse:
    return MerchantResponse(data=service.spending_by_merchant(query))


@router.get("/period-comparison", response_model=ComparisonResponse)
def compare_periods(
    service: Service, query: Annotated[ComparisonQuery, Query()]
) -> ComparisonResponse:
    return ComparisonResponse(data=service.compare_periods(query))
