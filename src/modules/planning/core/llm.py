from typing import Any

from langchain_openai import ChatOpenAI

from src.core.config import get_settings


def get_llm(
    temperature: float | None = None,
    model: str | None = None,
    **kwargs: Any,
) -> ChatOpenAI:
    settings = get_settings()
    temp = settings.llm_temperature if temperature is None else temperature
    client_kwargs: dict[str, Any] = {
        "model": model or settings.model_name,
        "api_key": settings.openai_api_key or None,
        "temperature": temp,
        # Bound provider connection/read time even when a caller forgets a
        # wait_for wrapper.  This is a safety property for the chat API.
        "request_timeout": kwargs.pop("request_timeout", settings.api_timeout_seconds),
        **kwargs,
    }
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    return ChatOpenAI(**client_kwargs)
