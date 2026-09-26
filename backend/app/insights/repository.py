from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select

from backend.app.insights.models import Insight
from backend.app.insights.schemas import InsightQuery
from backend.app.purchases.errors import NotFound
from backend.app.purchases.models import OutboxEvent
from backend.app.purchases.repositories import OwnedRepository


class InsightRepository(OwnedRepository):
    def get(self, insight_id: UUID, *, lock: bool = False) -> Insight:
        statement = select(Insight).where(
            Insight.id == insight_id, Insight.user_id == self._current_user.id
        )
        row = self._session.scalar(statement.with_for_update() if lock else statement)
        if row is None:
            raise NotFound
        return row

    def list(self, query: InsightQuery, now: datetime) -> list[Insight]:
        statement = select(Insight).where(Insight.user_id == self._current_user.id)
        if query.type is not None:
            statement = statement.where(Insight.type == query.type)
        active = Insight.status.in_(["ACTIVE", "READ"])
        if query.status is None:
            statement = statement.where(active, Insight.expires_at > now)
        elif query.status == "EXPIRED":
            statement = statement.where(
                or_(Insight.status == "EXPIRED", and_(active, Insight.expires_at <= now))
            )
        else:
            statement = statement.where(Insight.status == query.status)
            if query.status in {"ACTIVE", "READ"}:
                statement = statement.where(Insight.expires_at > now)
        return list(
            self._session.scalars(
                statement.order_by(Insight.created_at.desc(), Insight.id.desc())
                .limit(query.limit)
                .offset(query.offset)
            )
        )

    def scope(self, scope: str) -> Sequence[Insight]:
        return list(
            self._session.scalars(
                select(Insight)
                .where(Insight.user_id == self._current_user.id, Insight.scope == scope)
                .with_for_update()
            )
        )

    def add(self, row: Insight) -> None:
        if row.user_id != self._current_user.id:
            raise ValueError("Insight ownership mismatch")
        self._session.add(row)
        self._session.flush()
        self._session.add(
            OutboxEvent(
                user_id=self._current_user.id,
                insight_id=row.id,
                event_type="INSIGHT_CREATED",
                payload={"insight_id": str(row.id)},
                created_at=row.created_at,
                available_at=row.created_at,
            )
        )
