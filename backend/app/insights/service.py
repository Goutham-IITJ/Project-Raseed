import json
from collections.abc import Callable, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.identity.context import CurrentUser
from backend.app.insights.evaluation import Candidate
from backend.app.insights.generator import DeterministicInsightGenerator, InsightGenerator
from backend.app.insights.models import Insight
from backend.app.insights.repository import InsightRepository
from backend.app.insights.schemas import InsightQuery, InsightUpdate, InsightView
from backend.app.purchases.errors import Conflict, DomainError
from backend.app.purchases.queries import utc_now


def insight_view(row: Insight, now: datetime) -> InsightView:
    view = InsightView.model_validate(row)
    if view.status in {"ACTIVE", "READ"} and view.expires_at <= now:
        view.status = "EXPIRED"
    return view


class InsightService:
    def __init__(
        self,
        session: Session,
        user: CurrentUser,
        *,
        clock: Callable[[], datetime] = utc_now,
        generator: InsightGenerator | None = None,
    ) -> None:
        self.session, self.user, self.clock = session, user, clock
        self.repository = InsightRepository(session, user)
        self.generator = generator or DeterministicInsightGenerator()

    def list(self, query: InsightQuery) -> list[InsightView]:
        with self.session.begin():
            now = self.clock()
            return [insight_view(row, now) for row in self.repository.list(query, now)]

    def get(self, insight_id: UUID) -> InsightView:
        with self.session.begin():
            return insight_view(self.repository.get(insight_id), self.clock())

    def update(self, insight_id: UUID, data: InsightUpdate) -> InsightView:
        with self.session.begin():
            row = self.repository.get(insight_id, lock=True)
            now = self.clock()
            if row.version != data.expected_version:
                raise Conflict
            if row.status == data.status:
                return insight_view(row, now)
            if insight_view(row, now).status not in {"ACTIVE", "READ"}:
                raise Conflict
            row.status, row.updated_at = data.status, now
            row.version += 1
            if data.status == "READ":
                row.read_at = now
            else:
                row.dismissed_at = now
            self.session.flush()
            return insight_view(row, now)

    def record(self, scope: str, candidates: Sequence[Candidate], now: datetime) -> None:
        """Participate in the worker's owner-locked transaction and outbox acknowledgement."""
        if not self.session.in_transaction():
            raise RuntimeError("Insight recording requires the worker transaction")
        existing = {row.deduplication_key: row for row in self.repository.scope(scope)}
        for candidate in candidates:
            if (
                candidate.expires_at <= now
                or len(json.dumps(candidate.source, ensure_ascii=False).encode()) > 64 * 1024
                or len(json.dumps(candidate.calculation).encode()) > 4096
            ):
                raise DomainError
            title, summary = self.generator.explain(candidate.type, candidate.source)
            row = existing.pop(candidate.key, None)
            new = row is None
            if row is None:
                row = Insight(
                    user_id=self.user.id,
                    deduplication_key=candidate.key,
                    scope=scope,
                    type=candidate.type,
                    created_at=now,
                )
            else:
                row.version += 1
                if row.status in {"EXPIRED", "RESOLVED"}:
                    row.status = "ACTIVE"
                    row.read_at = None
            row.title, row.summary = title, summary
            row.source_data, row.calculation = candidate.source, candidate.calculation
            row.confidence = candidate.confidence
            row.evaluated_at = row.updated_at = now
            row.expires_at = candidate.expires_at
            if new:
                self.repository.add(row)
        for row in existing.values():
            if row.status not in {"ACTIVE", "READ"}:
                continue
            row.status = "EXPIRED" if row.expires_at <= now else "RESOLVED"
            row.updated_at = now
            row.version += 1
        self.session.flush()
