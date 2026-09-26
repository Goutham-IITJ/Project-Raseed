from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.identity.context import CurrentUser
from backend.app.memory.models import Memory
from backend.app.memory.relevance import relevance
from backend.app.memory.repository import MemoryRepository
from backend.app.memory.schemas import MemoryCreate, MemoryQuery, MemoryUpdate, MemoryView
from backend.app.purchases.errors import Conflict, DomainError
from backend.app.purchases.queries import utc_now
from backend.app.purchases.schemas import aware_utc


class MemoryService:
    def __init__(
        self,
        session: Session,
        current_user: CurrentUser,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.session, self.user, self.clock = session, current_user, clock
        self.repository = MemoryRepository(session, current_user)

    def _apply(self, row: Memory, data: MemoryCreate, now: datetime) -> None:
        if data.expires_at is not None and data.expires_at <= now:
            raise DomainError("Memory expiry must be in the future.")
        row.type, row.content, row.topics = data.type, data.content, list(data.topics)
        _, indexed_topics = relevance(data.content)
        row.search_text = " ".join(
            [data.type.casefold(), data.content, *data.topics, *indexed_topics]
        )
        row.source_conversation_id = self.repository.source(data.source_message_id)
        row.source_message_id, row.expires_at = data.source_message_id, data.expires_at
        row.updated_at = now

    def create(self, data: MemoryCreate) -> MemoryView:
        with self.session.begin():
            now = aware_utc(self.clock())
            row = Memory(user_id=self.user.id, created_at=now)
            self._apply(row, data, now)
            self.repository.add(row)
            return MemoryView.model_validate(row)

    def update(self, memory_id: UUID, data: MemoryUpdate) -> MemoryView:
        with self.session.begin():
            row = self.repository.get(memory_id, lock=True)
            if row.version != data.expected_version:
                raise Conflict
            self._apply(row, data, aware_utc(self.clock()))
            row.version += 1
            self.session.flush()
            return MemoryView.model_validate(row)

    def delete(self, memory_id: UUID, expected_version: int) -> None:
        with self.session.begin():
            row = self.repository.get(memory_id, lock=True)
            if row.version != expected_version:
                raise Conflict
            self.repository.delete(row)

    def get(self, memory_id: UUID) -> MemoryView:
        with self.session.begin():
            return MemoryView.model_validate(self.repository.get(memory_id))

    def list(self, query: MemoryQuery) -> list[MemoryView]:
        with self.session.begin():
            return [
                MemoryView.model_validate(row) for row in self.repository.list(query, self.clock())
            ]

    def relevant(self, content: str) -> tuple[MemoryView, ...]:
        query = content.strip()[:1000]
        if not query.strip():
            return ()
        rows = self.list(MemoryQuery(query=query, limit=5))
        selected: list[MemoryView] = []
        size = 0
        for row in rows:
            size += len(row.model_dump_json().encode("utf-8"))
            if size <= 8 * 1024:
                selected.append(row)
        return tuple(selected)
