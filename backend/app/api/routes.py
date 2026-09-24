from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_user_service, reject_query_parameters
from backend.app.identity.schemas import PreferencePatch, PreferencesResponse, UserResponse
from backend.app.identity.service import UserService

router = APIRouter(prefix="/api/v1/me")
Service = Annotated[UserService, Depends(get_user_service)]
NoQuery = Annotated[None, Depends(reject_query_parameters)]


@router.get("", response_model=UserResponse)
def me(service: Service, no_query: NoQuery) -> UserResponse:
    return UserResponse(data=service.get_user())


@router.get("/preferences", response_model=PreferencesResponse)
def preferences(service: Service, no_query: NoQuery) -> PreferencesResponse:
    return PreferencesResponse(data=service.get_preferences())


@router.patch("/preferences", response_model=PreferencesResponse)
def patch_preferences(
    patch: PreferencePatch, service: Service, no_query: NoQuery
) -> PreferencesResponse:
    return PreferencesResponse(data=service.patch_preferences(patch))
