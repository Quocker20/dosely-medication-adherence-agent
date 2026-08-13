from langchain_openai import ChatOpenAI

from src.config import get_settings


def get_llm(temperature: float | None = None) -> ChatOpenAI:
    """1 model dùng chung cho cả hệ thống (cong_viec.md §1) — chỉ đổi
    temperature theo từng node qua tham số này, không thêm model/config mới."""
    settings = get_settings()
    return ChatOpenAI(
        model=settings.model_name,
        api_key=settings.openai_api_key,
        temperature=settings.llm_temperature if temperature is None else temperature,
    )
