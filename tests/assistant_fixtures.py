import json
from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Annotated

from conftest import FakeVerifier
from fastapi import Depends

from backend.app.api.assistant import get_assistant_service
from backend.app.api.dependencies import get_current_user
from backend.app.assistant.model import ModelReply
from backend.app.assistant.schemas import FinalAnswer, ModelOutput, ToolCall, ValueReference
from backend.app.assistant.service import AssistantService
from backend.app.config import Settings
from backend.app.identity.context import CurrentUser
from backend.app.main import create_app

NOW = datetime(2026, 9, 26, 6, tzinfo=timezone.utc)
ALICE = {"Authorization": "Bearer alice-token"}
BOB = {"Authorization": "Bearer bob-token"}
ROOT = "/api/v1/assistant/conversations"


def final(
    template="How can I help with your recorded purchases?", *, sources=(), refs=(), kind=None
):
    return ModelReply(
        ModelOutput(
            answer=FinalAnswer(
                kind=kind or ("answer" if sources else "clarification"),
                template=template,
                source_call_ids=list(sources),
                references=[ValueReference.model_validate(ref) for ref in refs],
            )
        )
    )


def call(name="get_spending_summary", arguments=None, *, call_id="call_summary"):
    return ToolCall(
        call_id=call_id,
        name=name,
        arguments=json.dumps(arguments or {}) if not isinstance(arguments, str) else arguments,
    )


def calls(*values):
    return ModelReply(ModelOutput(tool_calls=list(values)))


def reference(pointer, *, name="value", call_id="call_summary"):
    return {"name": name, "call_id": call_id, "pointer": pointer}


class ScriptedModel:
    provider = "test"
    model = "scripted-model"

    def __init__(self, *steps):
        self.steps = deque(steps)
        self.requests = []
        self.timeouts = []
        self.lock = Lock()

    def respond(self, request, *, timeout):
        with self.lock:
            self.requests.append(request)
            self.timeouts.append(timeout)
            if not self.steps:
                raise AssertionError("Unexpected model invocation")
            step = self.steps.popleft()
        if isinstance(step, Exception):
            raise step
        return step(request) if callable(step) else step


def assistant_app(factory, model, **service_options):
    app = create_app(
        Settings(firebase_project_id="test-project", openai_api_key="", assistant_model=""),
        verifier=FakeVerifier(),
        session_factory=factory,
        assistant_model=model,
    )

    def service(current_user: Annotated[CurrentUser, Depends(get_current_user)]):
        return AssistantService(
            factory,
            current_user,
            model,
            **{"clock": lambda: NOW, "sleep": lambda _: None, **service_options},
        )

    app.dependency_overrides[get_assistant_service] = service
    return app
