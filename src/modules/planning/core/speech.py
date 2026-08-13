"""Speech I/O — STT (giọng nói -> chữ) và TTS (chữ -> giọng nói), cho bệnh
nhân cao tuổi không muốn/không tiện gõ chữ.

Đây là lớp CHUYỂN ĐỔI bọc quanh graph chat (src/agents/graph.py), KHÔNG
phải tool cho LLM tự quyết định gọi — LLM không cần biết audio tồn tại, nó
luôn chỉ thấy/chỉ tạo text. Việc audio<->text xảy ra ở tầng API
(src/modules/agents/router.py), trước khi vào và sau khi ra khỏi graph.

Nguyên tắc lỗi: transcribe_audio KHÔNG fail-open — nghe không rõ thì phải
raise rõ ràng để tầng gọi báo bệnh nhân nói lại, không được âm thầm coi
như "không nói gì" (một câu mô tả triệu chứng bị nuốt mất vì lỗi STT là
nguy hiểm). synthesize_speech cũng raise khi lỗi — tầng gọi (route) tự
quyết định có fallback về text-only hay không, không quyết định hộ ở đây.
"""
from __future__ import annotations

from openai import AsyncOpenAI

from src.core.config import get_settings


class SpeechServiceError(Exception):
    """STT hoặc TTS gọi OpenAI thất bại."""


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=get_settings().openai_api_key)


async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """Audio -> text (Speech-to-Text).

    Args:
        audio_bytes: nội dung file audio thô (webm/mp3/wav/m4a...)
        filename: tên file kèm đuôi, OpenAI dùng để đoán định dạng

    Returns:
        Văn bản đã nhận dạng, đã strip khoảng trắng thừa.

    Raises:
        SpeechServiceError: gọi OpenAI thất bại (mạng, quota, audio hỏng...).
    """
    settings = get_settings()
    try:
        transcript = await _client().audio.transcriptions.create(
            model=settings.stt_model,
            file=(filename, audio_bytes),
            language="vi",
        )
    except Exception as e:
        raise SpeechServiceError(f"Không nhận dạng được giọng nói: {e}") from e
    return transcript.text.strip()


async def synthesize_speech(text: str) -> bytes:
    """Text -> audio (Text-to-Speech).

    Args:
        text: nội dung cần đọc thành giọng nói

    Returns:
        Bytes audio (mp3).

    Raises:
        SpeechServiceError: gọi OpenAI thất bại.
    """
    settings = get_settings()
    try:
        response = await _client().audio.speech.create(
            model=settings.tts_model,
            voice=settings.tts_voice,
            input=text,
        )
    except Exception as e:
        raise SpeechServiceError(f"Không tạo được giọng nói: {e}") from e
    return await response.aread()
