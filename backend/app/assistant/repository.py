from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from backend.app.assistant.models import Conversation, Message, ToolExecution
from backend.app.purchases.errors import NotFound
from backend.app.purchases.repositories import OwnedRepository
from backend.app.purchases.schemas import PageQuery


class AssistantRepository(OwnedRepository):
    def conversation(self, conversation_id: UUID, *, for_update: bool = False) -> Conversation:
        statement = select(Conversation).where(
            Conversation.user_id == self._current_user.id, Conversation.id == conversation_id
        )
        if for_update:
            statement = statement.with_for_update()
        row = self._session.scalar(statement)
        if row is None:
            raise NotFound
        return row

    def create_conversation(self, title: str | None, now: datetime) -> Conversation:
        row = Conversation(
            user_id=self._current_user.id, title=title, created_at=now, updated_at=now
        )
        self._session.add(row)
        self._session.flush()
        return row

    def messages(self, conversation_id: UUID, page: PageQuery) -> Sequence[Message]:
        return self._session.scalars(
            select(Message)
            .where(
                Message.user_id == self._current_user.id, Message.conversation_id == conversation_id
            )
            .order_by(Message.sequence)
            .limit(page.limit)
            .offset(page.offset)
        ).all()

    def message(self, conversation_id: UUID, message_id: UUID, *, lock: bool = False) -> Message:
        statement = select(Message).where(
            Message.user_id == self._current_user.id,
            Message.conversation_id == conversation_id,
            Message.id == message_id,
        )
        if lock:
            statement = statement.with_for_update()
        row = self._session.scalar(statement)
        if row is None:
            raise NotFound
        return row

    def prior_request(self, conversation_id: UUID, key: UUID) -> Message | None:
        return self._session.scalar(
            select(Message).where(
                Message.user_id == self._current_user.id,
                Message.conversation_id == conversation_id,
                Message.idempotency_key == key,
            )
        )

    def reply(self, conversation_id: UUID, user_message_id: UUID) -> Message:
        return self._session.scalars(
            select(Message).where(
                Message.user_id == self._current_user.id,
                Message.conversation_id == conversation_id,
                Message.reply_to_id == user_message_id,
            )
        ).one()

    def active(self, conversation_id: UUID) -> Message | None:
        return self._session.scalar(
            select(Message)
            .where(
                Message.user_id == self._current_user.id,
                Message.conversation_id == conversation_id,
                Message.status == "PROCESSING",
            )
            .with_for_update()
        )

    def history(self, conversation_id: UUID, before_sequence: int) -> Sequence[Message]:
        return self._session.scalars(
            select(Message)
            .where(
                Message.user_id == self._current_user.id,
                Message.conversation_id == conversation_id,
                Message.sequence < before_sequence,
                Message.status == "COMPLETED",
            )
            .order_by(Message.sequence.desc())
            .limit(19)  # The current user message is the twentieth context message.
        ).all()

    def executions(
        self, conversation_id: UUID, message_ids: Sequence[UUID]
    ) -> Sequence[ToolExecution]:
        return self._session.scalars(
            select(ToolExecution)
            .where(
                ToolExecution.user_id == self._current_user.id,
                ToolExecution.conversation_id == conversation_id,
                ToolExecution.message_id.in_(message_ids),
            )
            .order_by(ToolExecution.started_at, ToolExecution.id)
        ).all()

    def execution(
        self, conversation_id: UUID, message_id: UUID, call_id: str
    ) -> ToolExecution | None:
        return self._session.scalar(
            select(ToolExecution).where(
                ToolExecution.user_id == self._current_user.id,
                ToolExecution.conversation_id == conversation_id,
                ToolExecution.message_id == message_id,
                ToolExecution.call_id == call_id,
            )
        )

    def add_message(self, message: Message) -> None:
        if message.user_id != self._current_user.id:
            raise ValueError("Message ownership mismatch")
        self._session.add(message)
        self._session.flush()

    def add_execution(self, execution: ToolExecution) -> None:
        if execution.user_id != self._current_user.id:
            raise ValueError("Tool ownership mismatch")
        self._session.add(execution)
        self._session.flush()
