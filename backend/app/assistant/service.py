"""Bounded assistant orchestration with short transactions and durable execution leases."""

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.orm import Session, sessionmaker

from backend.app.assistant.errors import AssistantFailure, ConversationBusy, ModelFailure, StaleTurn
from backend.app.assistant.grounding import ground_answer
from backend.app.assistant.json import call_hash
from backend.app.assistant.model import (
    AssistantModel,
    ContextMessage,
    ModelContext,
    ModelReply,
    ModelRequest,
    ToolFeedback,
)
from backend.app.assistant.models import Conversation, Message, ToolExecution
from backend.app.assistant.prompt import PROMPT
from backend.app.assistant.repository import AssistantRepository
from backend.app.assistant.schemas import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    ConversationCreate,
    ConversationView,
    FinalAnswer,
    MessageCreate,
    MessageView,
    ModelOutput,
    ToolCall,
    ToolExecutionView,
    ToolResult,
    TurnView,
)
from backend.app.assistant.tools import ToolContext, ToolRegistry
from backend.app.identity.context import CurrentUser
from backend.app.identity.repositories import PreferencesRepository
from backend.app.memory.service import MemoryService
from backend.app.purchases.errors import Conflict
from backend.app.purchases.queries import utc_now
from backend.app.purchases.schemas import PageQuery, aware_utc

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssistantLimits:
    max_rounds: int = 6
    max_tool_calls: int = 8
    max_attempts: int = 2
    request_timeout: float = 20
    turn_timeout: float = 120


@dataclass(frozen=True)
class TurnLease:
    conversation_id: UUID
    message_id: UUID
    token: UUID
    started_at: datetime


class AssistantService:
    def __init__(
        self,
        factory: sessionmaker[Session],
        current_user: CurrentUser,
        model: AssistantModel,
        *,
        registry: ToolRegistry | None = None,
        limits: AssistantLimits | None = None,
        clock: Callable[[], datetime] = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._factory, self._user, self._model = factory, current_user, model
        self._registry, self._limits = registry or ToolRegistry(), limits or AssistantLimits()
        self._clock, self._monotonic, self._sleep = clock, monotonic, sleep

    def _now(self) -> datetime:
        return aware_utc(self._clock())

    def create_conversation(self, data: ConversationCreate) -> ConversationView:
        with self._factory() as session, session.begin():
            repository = AssistantRepository(session, self._user)
            return ConversationView.model_validate(
                repository.create_conversation(data.title, self._now())
            )

    def get_conversation(self, conversation_id: UUID) -> ConversationView:
        with self._factory() as session, session.begin():
            return ConversationView.model_validate(
                AssistantRepository(session, self._user).conversation(conversation_id)
            )

    def list_messages(self, conversation_id: UUID, page: PageQuery) -> list[MessageView]:
        with self._factory() as session, session.begin():
            repository = AssistantRepository(session, self._user)
            repository.conversation(conversation_id)
            return self._views(
                repository, conversation_id, repository.messages(conversation_id, page)
            )

    def _views(
        self, repository: AssistantRepository, conversation_id: UUID, rows: Sequence[Message]
    ) -> list[MessageView]:
        executions: dict[UUID, list[ToolExecutionView]] = {}
        for execution in repository.executions(conversation_id, [row.id for row in rows]):
            executions.setdefault(execution.message_id, []).append(
                ToolExecutionView.model_validate(execution)
            )
        return [
            MessageView.model_validate(
                {
                    **{
                        name: getattr(row, name)
                        for name in MessageView.model_fields
                        if name not in {"provenance", "tool_executions"}
                    },
                    "provenance": "OBSERVED" if row.role == "USER" else "INFERRED",
                    "tool_executions": executions.get(row.id, []),
                }
            )
            for row in rows
        ]

    def _turn(self, repository: AssistantRepository, reply: Message, *, replayed: bool) -> TurnView:
        assert reply.reply_to_id is not None
        user_message = repository.message(reply.conversation_id, reply.reply_to_id)
        user_view, reply_view = self._views(
            repository, reply.conversation_id, [user_message, reply]
        )
        return TurnView(user_message=user_view, assistant_message=reply_view, replayed=replayed)

    def _fail_record(
        self, repository: AssistantRepository, reply: Message, code: str, now: datetime
    ) -> None:
        error = AssistantFailure(code)
        reply.status = "FAILED"
        reply.content, reply.evidence = None, None
        reply.failure_code, reply.failure_message = code, error.message
        reply.completed_at = max(reply.created_at, now)
        reply.lease_token, reply.lease_expires_at = None, None
        for execution in repository.executions(reply.conversation_id, [reply.id]):
            if execution.status != "RUNNING":
                continue
            execution.status = "FAILED"
            execution.completed_at = max(execution.started_at, now)
            execution.elapsed_ms = max(
                0, int((execution.completed_at - execution.started_at).total_seconds() * 1000)
            )
            execution.result = ToolResult.failure(
                "execution_interrupted", "Tool execution was interrupted; no result is available."
            ).model_dump(mode="json")

    def _reserve(
        self, conversation_id: UUID, data: MessageCreate
    ) -> tuple[TurnView, TurnLease | None]:
        with self._factory() as session, session.begin():
            repository = AssistantRepository(session, self._user)
            conversation = repository.conversation(conversation_id, for_update=True)
            now = self._now()
            active = repository.active(conversation_id)
            if (
                active is not None
                and active.lease_expires_at is not None
                and active.lease_expires_at <= now
            ):
                self._fail_record(repository, active, "request_expired", now)
                conversation.updated_at = max(conversation.updated_at, now)
                # Release active-turn uniqueness before reserving again.
                session.flush()
                active = None
            prior = repository.prior_request(conversation_id, data.idempotency_key)
            if prior is not None:
                if prior.content != data.content:
                    raise Conflict
                reply = repository.reply(conversation_id, prior.id)
                return self._turn(repository, reply, replayed=True), None
            if active is not None:
                raise ConversationBusy
            user_message = Message(
                id=uuid4(),
                user_id=self._user.id,
                conversation_id=conversation_id,
                sequence=conversation.next_sequence,
                role="USER",
                status="COMPLETED",
                content=data.content,
                idempotency_key=data.idempotency_key,
                created_at=now,
                completed_at=now,
            )
            repository.add_message(user_message)
            token = uuid4()
            reply = Message(
                id=uuid4(),
                user_id=self._user.id,
                conversation_id=conversation_id,
                sequence=conversation.next_sequence + 1,
                role="ASSISTANT",
                status="PROCESSING",
                reply_to_id=user_message.id,
                provider=self._model.provider,
                model=self._model.model or None,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                lease_token=token,
                lease_expires_at=now + timedelta(seconds=self._limits.turn_timeout + 30),
                created_at=now,
            )
            repository.add_message(reply)
            conversation.next_sequence += 2
            conversation.updated_at = max(conversation.updated_at, now)
            return self._turn(repository, reply, replayed=False), TurnLease(
                conversation_id, reply.id, token, now
            )

    def _active(
        self, repository: AssistantRepository, lease: TurnLease
    ) -> tuple[Conversation, Message]:
        # All writes acquire conversation then message locks in this order.
        conversation = repository.conversation(lease.conversation_id, for_update=True)
        reply = repository.message(lease.conversation_id, lease.message_id, lock=True)
        if (
            reply.status != "PROCESSING"
            or reply.lease_token != lease.token
            or reply.lease_expires_at is None
            or reply.lease_expires_at <= self._now()
        ):
            raise StaleTurn
        return conversation, reply

    def _remaining(self, deadline: float) -> float:
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            raise AssistantFailure("assistant_timeout")
        return remaining

    def _context(
        self, lease: TurnLease, user_message: MessageView
    ) -> tuple[ModelContext, tuple[ContextMessage, ...]]:
        assert user_message.content is not None
        with self._factory() as memory_session:
            memories = MemoryService(
                memory_session, self._user, clock=lambda: lease.started_at
            ).relevant(user_message.content)
        with self._factory() as session, session.begin():
            repository = AssistantRepository(session, self._user)
            self._active(repository, lease)
            preferences = PreferencesRepository(session, self._user).get()
            context = ModelContext(
                lease.started_at,
                preferences.timezone,
                preferences.currency,
                preferences.locale,
                tuple(
                    memory.model_dump(mode="json", exclude={"source_message_id"})
                    for memory in memories
                ),
            )
            assert user_message.content is not None
            history = [ContextMessage("user", user_message.content)]
            size = len(user_message.content.encode("utf-8"))
            for row in repository.history(lease.conversation_id, user_message.sequence):
                assert row.content is not None
                size += len(row.content.encode("utf-8"))
                if size > 64 * 1024:
                    break
                history.append(
                    ContextMessage("user" if row.role == "USER" else "assistant", row.content)
                )
            return context, tuple(reversed(history))

    def _respond(self, lease: TurnLease, request: ModelRequest, deadline: float) -> ModelReply:
        for attempt in range(self._limits.max_attempts):
            timeout = min(self._limits.request_timeout, self._remaining(deadline))
            with self._factory() as session, session.begin():
                _, message = self._active(AssistantRepository(session, self._user), lease)
                message.model_attempts += 1
            try:
                reply = self._model.respond(request, timeout=timeout)
            except ModelFailure as exc:
                if not exc.retryable or attempt + 1 == self._limits.max_attempts:
                    raise AssistantFailure(exc.code) from exc
                delay = min(0.25 * (2**attempt), 1)
                if delay >= self._remaining(deadline):
                    raise AssistantFailure("assistant_timeout") from exc
                self._sleep(delay)
                continue
            except Exception as exc:
                logger.error("Assistant provider failed (%s)", type(exc).__name__)
                raise AssistantFailure("model_unavailable") from exc
            self._remaining(deadline)
            try:
                # Validate again at the application boundary, including injected adapters.
                output = ModelOutput.model_validate(reply.output.model_dump())
                return ModelReply(output, reply.continuation)
            except (AttributeError, ValueError, TypeError) as exc:
                raise AssistantFailure("model_invalid_output") from exc
        raise AssistantFailure("assistant_limit")

    def _tool(self, lease: TurnLease, call: ToolCall, deadline: float) -> ToolFeedback:
        self._remaining(deadline)
        digest = call_hash(call.name, call.arguments)
        with self._factory() as session, session.begin():
            repository = AssistantRepository(session, self._user)
            self._active(repository, lease)
            prior = repository.execution(lease.conversation_id, lease.message_id, call.call_id)
            if prior is not None:
                if prior.request_hash != digest or prior.status == "RUNNING":
                    raise AssistantFailure("tool_call_conflict")
                return ToolFeedback(call.call_id, ToolResult.model_validate(prior.result))
            execution = ToolExecution(
                id=uuid4(),
                user_id=self._user.id,
                conversation_id=lease.conversation_id,
                message_id=lease.message_id,
                call_id=call.call_id,
                tool_name=call.name,
                raw_arguments=call.arguments,
                request_hash=digest,
                status="RUNNING",
                started_at=self._now(),
            )
            repository.add_execution(execution)
        started = self._monotonic()
        with self._factory() as session:
            outcome = self._registry.invoke(
                ToolContext(session, self._user, lease.started_at), call
            )
        elapsed = max(0, int((self._monotonic() - started) * 1000))
        with self._factory() as session, session.begin():
            repository = AssistantRepository(session, self._user)
            self._active(repository, lease)
            row = repository.execution(lease.conversation_id, lease.message_id, call.call_id)
            assert row is not None and row.status == "RUNNING"
            row.arguments = outcome.arguments
            row.status = outcome.result.status
            row.result = outcome.result.model_dump(mode="json")
            row.completed_at = max(row.started_at, self._now())
            row.elapsed_ms = elapsed
            session.flush()
            return ToolFeedback(call.call_id, ToolResult.model_validate(row.result))

    def _complete(self, lease: TurnLease, answer: FinalAnswer, deadline: float) -> None:
        self._remaining(deadline)
        with self._factory() as session, session.begin():
            repository = AssistantRepository(session, self._user)
            conversation, reply = self._active(repository, lease)
            content, evidence = ground_answer(
                answer, repository.executions(lease.conversation_id, [lease.message_id])
            )
            reply.content, reply.evidence = content, evidence.model_dump(mode="json")
            reply.status = "COMPLETED"
            reply.completed_at = max(reply.created_at, self._now())
            reply.lease_token, reply.lease_expires_at = None, None
            conversation.updated_at = max(conversation.updated_at, reply.completed_at)

    def _run(self, lease: TurnLease, user_message: MessageView, deadline: float) -> None:
        context, history = self._context(lease, user_message)
        continuation: object | None = None
        feedback: tuple[ToolFeedback, ...] = ()
        invocations = 0
        for _ in range(self._limits.max_rounds):
            reply = self._respond(
                lease,
                ModelRequest(
                    PROMPT, context, history, self._registry.definitions(), feedback, continuation
                ),
                deadline,
            )
            if reply.output.answer is not None:
                self._complete(lease, reply.output.answer, deadline)
                return
            invocations += len(reply.output.tool_calls)
            if invocations > self._limits.max_tool_calls:
                raise AssistantFailure("assistant_limit")
            feedback = tuple(self._tool(lease, call, deadline) for call in reply.output.tool_calls)
            continuation = reply.continuation
        raise AssistantFailure("assistant_limit")

    def _fail(self, lease: TurnLease, code: str) -> None:
        with self._factory() as session, session.begin():
            repository = AssistantRepository(session, self._user)
            conversation = repository.conversation(lease.conversation_id, for_update=True)
            reply = repository.message(lease.conversation_id, lease.message_id, lock=True)
            if reply.status != "PROCESSING" or reply.lease_token != lease.token:
                return  # A recovered or completed reply must never be overwritten.
            now = self._now()
            if reply.lease_expires_at is not None and reply.lease_expires_at <= now:
                code = "request_expired"
            self._fail_record(repository, reply, code, now)
            conversation.updated_at = max(conversation.updated_at, now)

    def submit_message(self, conversation_id: UUID, data: MessageCreate) -> TurnView:
        deadline = self._monotonic() + self._limits.turn_timeout
        view, lease = self._reserve(conversation_id, data)
        if lease is not None:
            try:
                self._run(lease, view.user_message, deadline)
            except AssistantFailure as exc:
                self._fail(lease, exc.code)
            except StaleTurn:
                self._fail(lease, "request_expired")
            except Exception as exc:
                logger.error("Assistant execution failed (%s)", type(exc).__name__)
                self._fail(lease, "assistant_unavailable")
            with self._factory() as session, session.begin():
                repository = AssistantRepository(session, self._user)
                reply = repository.message(conversation_id, lease.message_id)
                view = self._turn(repository, reply, replayed=False)
        if view.assistant_message.status == "FAILED":
            assert view.assistant_message.failure_code is not None
            raise AssistantFailure(view.assistant_message.failure_code)
        return view
