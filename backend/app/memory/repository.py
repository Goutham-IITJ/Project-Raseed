from datetime import datetime
from uuid import UUID

from sqlalchemy import case, func, literal_column, or_, select

from backend.app.assistant.models import Message
from backend.app.memory.models import Memory
from backend.app.memory.relevance import relevance
from backend.app.memory.schemas import MemoryQuery
from backend.app.purchases.errors import NotFound
from backend.app.purchases.repositories import OwnedRepository


class MemoryRepository(OwnedRepository):
    def get(self, memory_id: UUID, *, lock: bool = False) -> Memory:
        query = select(Memory).where(
            Memory.id == memory_id, Memory.user_id == self._current_user.id
        )
        row = self._session.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise NotFound
        return row

    def source(self, message_id: UUID | None) -> UUID | None:
        if message_id is None:
            return None
        conversation_id = self._session.scalar(
            select(Message.conversation_id).where(
                Message.id == message_id,
                Message.user_id == self._current_user.id,
                Message.role == "USER",
            )
        )
        if conversation_id is None:
            raise NotFound
        return conversation_id

    def list(self, query: MemoryQuery, now: datetime) -> list[Memory]:
        statement = select(Memory).where(Memory.user_id == self._current_user.id)
        if not query.include_expired:
            statement = statement.where(or_(Memory.expires_at.is_(None), Memory.expires_at > now))
        if query.type is not None:
            statement = statement.where(Memory.type == query.type)
        if query.query is not None:
            terms, topics = relevance(query.query)
            if not terms and not topics:
                return []
            vector = func.to_tsvector(literal_column("'simple'"), Memory.search_text)
            search = func.to_tsquery(
                literal_column("'simple'"), " | ".join(sorted(set(terms + topics)))
            )
            topic_match = Memory.topics.overlap(topics)
            statement = statement.where(or_(vector.op("@@")(search), topic_match)).order_by(
                (func.ts_rank(vector, search) + case((topic_match, 1), else_=0)).desc()
            )
        return list(
            self._session.scalars(
                statement.order_by(Memory.updated_at.desc(), Memory.id.desc())
                .limit(query.limit)
                .offset(query.offset)
            )
        )

    def add(self, memory: Memory) -> None:
        if memory.user_id != self._current_user.id:
            raise ValueError("Memory ownership mismatch")
        self._session.add(memory)
        self._session.flush()

    def delete(self, memory: Memory) -> None:
        if memory.user_id != self._current_user.id:
            raise ValueError("Memory ownership mismatch")
        self._session.delete(memory)
