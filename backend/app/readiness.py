"""Local readiness only; provider acceptance is verified through real workflows."""

import os
from functools import lru_cache

from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import ROOT, Settings, configured


@lru_cache(maxsize=1)
def schema_heads() -> frozenset[str]:
    return frozenset(ScriptDirectory(str(ROOT / "database" / "migrations")).get_heads())


def is_ready(settings: Settings, factory: sessionmaker[Session]) -> bool:
    if not settings.local_demo and (
        not configured(settings.firebase_project_id) or os.getenv("FIREBASE_AUTH_EMULATOR_HOST")
    ):
        return False
    try:
        with factory.begin() as session:
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
            revisions = frozenset(session.scalars(text("SELECT version_num FROM alembic_version")))
        return revisions == schema_heads()
    except SQLAlchemyError:
        return False
