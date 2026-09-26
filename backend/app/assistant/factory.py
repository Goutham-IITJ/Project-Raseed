from backend.app.assistant.openai import OpenAIAssistantModel
from backend.app.config import Settings


def make_assistant_model(settings: Settings) -> OpenAIAssistantModel:
    return OpenAIAssistantModel(
        settings.openai_api_key.get_secret_value(),
        settings.assistant_model,
        max_output_tokens=settings.assistant_max_output_tokens,
    )
