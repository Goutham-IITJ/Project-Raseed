from backend.app.purchases.errors import Conflict, DomainError

FAILURES: dict[str, tuple[int, str]] = {
    "provider_configuration": (503, "Assistant provider is not configured."),
    "model_unavailable": (503, "Assistant provider is temporarily unavailable."),
    "model_timeout": (504, "Assistant provider timed out."),
    "model_invalid_output": (502, "Assistant provider returned an invalid response."),
    "model_refused": (502, "Assistant provider could not answer this request."),
    "assistant_limit": (502, "Assistant reached its execution limit. Try a narrower question."),
    "assistant_timeout": (504, "Assistant reached its time limit. Please try again."),
    "request_expired": (504, "Assistant execution expired. Submit a new message to retry."),
    "tool_call_conflict": (502, "Assistant reused a tool call identifier inconsistently."),
    "assistant_unavailable": (503, "Assistant execution is temporarily unavailable."),
}


class AssistantFailure(DomainError):
    def __init__(self, code: str) -> None:
        self.status_code, self.message = FAILURES[code]
        self.code = code
        super().__init__(self.message)


class ModelFailure(Exception):
    """Adapter errors carry only fixed, safe codes, never a provider response body."""

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        if code not in FAILURES:
            raise ValueError("Unknown assistant failure code")
        self.code, self.retryable = code, retryable
        super().__init__(code)


class ConversationBusy(Conflict):
    message = "This conversation already has a message being processed."


class StaleTurn(Exception):
    """A worker no longer has permission to write this reserved reply."""
