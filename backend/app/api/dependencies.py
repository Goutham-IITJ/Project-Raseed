from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, sessionmaker

from backend.app.identity.context import (
    CurrentUser,
    InvalidToken,
    TokenVerifier,
    VerificationUnavailable,
    VerifiedIdentity,
)
from backend.app.identity.service import UserService, provision_user

bearer = HTTPBearer(auto_error=False)


def get_verifier(request: Request) -> TokenVerifier:
    return cast(TokenVerifier, request.app.state.token_verifier)


def get_verified_identity(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    verifier: Annotated[TokenVerifier, Depends(get_verifier)],
) -> VerifiedIdentity:
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not credentials.credentials
        or any(character.isspace() for character in credentials.credentials)
    ):
        raise HTTPException(401, headers={"WWW-Authenticate": "Bearer"})
    try:
        return verifier.verify(credentials.credentials)
    except InvalidToken as exc:
        raise HTTPException(401, headers={"WWW-Authenticate": "Bearer"}) from exc
    except VerificationUnavailable as exc:
        raise HTTPException(503, detail="authentication_unavailable") from exc


def get_session(request: Request) -> Iterator[Session]:
    factory = cast(sessionmaker[Session], request.app.state.session_factory)
    with factory() as session:
        yield session


def get_current_user(
    identity: Annotated[VerifiedIdentity, Depends(get_verified_identity)],
    session: Annotated[Session, Depends(get_session)],
) -> CurrentUser:
    return provision_user(session, identity)


def get_user_service(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> UserService:
    return UserService(session, current_user)


def reject_query_parameters(request: Request) -> None:
    if request.query_params:
        raise HTTPException(422, detail="validation_error")
