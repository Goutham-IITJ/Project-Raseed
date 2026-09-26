from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user, get_session, reject_query_parameters
from backend.app.identity.context import CurrentUser
from backend.app.memory.schemas import (
    MemoryCreate,
    MemoryListResponse,
    MemoryQuery,
    MemoryResponse,
    MemoryUpdate,
    MemoryVersion,
)
from backend.app.memory.service import MemoryService

router = APIRouter(prefix="/api/v1/memories", tags=["Memory"])


def get_memory_service(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> MemoryService:
    return MemoryService(session, user)


Service = Annotated[MemoryService, Depends(get_memory_service)]
NoQuery = Annotated[None, Depends(reject_query_parameters)]


@router.post("", response_model=MemoryResponse, status_code=201)
def create_memory(data: MemoryCreate, service: Service, no_query: NoQuery) -> MemoryResponse:
    return MemoryResponse(data=service.create(data))


@router.get("", response_model=MemoryListResponse)
def list_memories(service: Service, query: Annotated[MemoryQuery, Query()]) -> MemoryListResponse:
    return MemoryListResponse(data=service.list(query))


@router.get("/{memory_id}", response_model=MemoryResponse)
def get_memory(memory_id: UUID, service: Service, no_query: NoQuery) -> MemoryResponse:
    return MemoryResponse(data=service.get(memory_id))


@router.patch("/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: UUID, data: MemoryUpdate, service: Service, no_query: NoQuery
) -> MemoryResponse:
    return MemoryResponse(data=service.update(memory_id, data))


@router.delete("/{memory_id}", status_code=204)
def delete_memory(
    memory_id: UUID, service: Service, query: Annotated[MemoryVersion, Query()]
) -> Response:
    service.delete(memory_id, query.expected_version)
    return Response(status_code=204)
