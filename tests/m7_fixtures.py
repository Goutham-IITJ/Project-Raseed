from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Annotated

import pytest
from assistant_fixtures import ScriptedModel, assistant_app
from fastapi import Depends
from sqlalchemy.orm import Session
from test_purchase_validation import purchase_data

from backend.app.api.dependencies import get_current_user, get_session
from backend.app.api.insights import get_insight_service
from backend.app.api.memory import get_memory_service
from backend.app.database import make_session_factory
from backend.app.identity.context import CurrentUser, VerifiedIdentity
from backend.app.identity.service import provision_user
from backend.app.insights.service import InsightService
from backend.app.memory.service import MemoryService
from backend.app.purchases.schemas import PurchaseCreate
from backend.app.purchases.service import PurchaseService

NOW = datetime(2030, 9, 26, 6, tzinfo=timezone.utc)
ALICE = {"Authorization": "Bearer alice-token"}
BOB = {"Authorization": "Bearer bob-token"}


@pytest.fixture
def environment(database):
    factory = make_session_factory(database)
    with factory() as session:
        alice = provision_user(session, VerifiedIdentity("firebase-alice"))
        bob = provision_user(session, VerifiedIdentity("firebase-bob"))
    return SimpleNamespace(database=database, factory=factory, alice=alice, bob=bob)


def app_for(env, model=None):
    app = assistant_app(env.factory, model or ScriptedModel(), clock=lambda: NOW)

    def memory(
        user: Annotated[CurrentUser, Depends(get_current_user)],
        session: Annotated[Session, Depends(get_session)],
    ):
        return MemoryService(session, user, clock=lambda: NOW)

    def insights(
        user: Annotated[CurrentUser, Depends(get_current_user)],
        session: Annotated[Session, Depends(get_session)],
    ):
        return InsightService(session, user, clock=lambda: NOW)

    app.dependency_overrides[get_memory_service] = memory
    app.dependency_overrides[get_insight_service] = insights
    return app


def purchase(env, *, owner=None, at=NOW, amount="10", currency="INR", **changes):
    with env.factory() as session:
        return PurchaseService(session, owner or env.alice).create_purchase(
            PurchaseCreate.model_validate(
                purchase_data(purchased_at=at, grand_total=amount, currency=currency, **changes)
            )
        )


def date_at(month, day=10):
    return datetime(2030, month, day, 6, tzinfo=timezone.utc)


def spending_fixture(env):
    for _ in range(3):
        purchase(env, at=date_at(7), amount="100")
        purchase(env, at=date_at(8), amount="150")
        purchase(env, owner=env.bob, at=date_at(8), amount="9999")
    for _ in range(5):
        purchase(env, at=date_at(9, 5), amount="10")
    purchase(env, at=date_at(9, 25), amount="30")
