from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session, sessionmaker

from backend.app.api.dependencies import get_current_user, reject_query_parameters
from backend.app.assistant.model import AssistantModel
from backend.app.assistant.schemas import (
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    MessageCreate,
    MessageListResponse,
    TurnResponse,
)
from backend.app.assistant.service import AssistantLimits, AssistantService
from backend.app.config import Settings
from backend.app.identity.context import CurrentUser
from backend.app.purchases.schemas import PageQuery

router = APIRouter(prefix="/api/v1/assistant/conversations", tags=["Assistant"])


def get_assistant_service(
    request: Request, current_user: Annotated[CurrentUser, Depends(get_current_user)]
) -> AssistantService:
    settings = cast(Settings, request.app.state.settings)
    return AssistantService(
        cast(sessionmaker[Session], request.app.state.session_factory),
        current_user,
        cast(AssistantModel, request.app.state.assistant_model),
        limits=AssistantLimits(
            max_rounds=settings.assistant_max_rounds,
            max_tool_calls=settings.assistant_max_tool_calls,
            max_attempts=settings.assistant_max_attempts,
            request_timeout=settings.assistant_request_timeout_seconds,
            turn_timeout=settings.assistant_turn_timeout_seconds,
        ),
    )


Service = Annotated[AssistantService, Depends(get_assistant_service)]
NoQuery = Annotated[None, Depends(reject_query_parameters)]


@router.get("", response_model=ConversationListResponse)
def list_conversations(
    service: Service, page: Annotated[PageQuery, Query()]
) -> ConversationListResponse:
    return ConversationListResponse(data=service.list_conversations(page))


@router.post("", response_model=ConversationResponse, status_code=201)
def create_conversation(
    data: ConversationCreate, service: Service, no_query: NoQuery
) -> ConversationResponse:
    return ConversationResponse(data=service.create_conversation(data))


@router.get("/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: UUID, service: Service, no_query: NoQuery
) -> ConversationResponse:
    return ConversationResponse(data=service.get_conversation(conversation_id))


@router.post("/{conversation_id}/messages", response_model=TurnResponse, status_code=201)
def post_message(
    conversation_id: UUID,
    data: MessageCreate,
    service: Service,
    no_query: NoQuery,
    response: Response,
) -> TurnResponse:
    turn = service.submit_message(conversation_id, data)
    if turn.assistant_message.status == "PROCESSING":
        response.status_code = 202
    elif turn.replayed:
        response.status_code = 200
    return TurnResponse(data=turn)


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
def list_messages(
    conversation_id: UUID, service: Service, page: Annotated[PageQuery, Query()]
) -> MessageListResponse:
    return MessageListResponse(data=service.list_messages(conversation_id, page))
