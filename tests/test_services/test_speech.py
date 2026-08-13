from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.modules.planning.core.speech import SpeechServiceError, synthesize_speech, transcribe_audio


def _mock_client():
    patcher = patch("src.modules.planning.core.speech.AsyncOpenAI")
    mock_cls = patcher.start()
    mock_instance = MagicMock()
    mock_cls.return_value = mock_instance
    return patcher, mock_instance


@pytest.mark.asyncio
async def test_transcribe_audio_returns_stripped_text():
    patcher, client = _mock_client()
    client.audio.transcriptions.create = AsyncMock(
        return_value=MagicMock(text="  xin chào, tôi bị đau bụng  ")
    )
    try:
        result = await transcribe_audio(b"fake-bytes", filename="rec.webm")
    finally:
        patcher.stop()

    assert result == "xin chào, tôi bị đau bụng"
    client.audio.transcriptions.create.assert_called_once()
    _, kwargs = client.audio.transcriptions.create.call_args
    assert kwargs["file"] == ("rec.webm", b"fake-bytes")
    assert kwargs["language"] == "vi"


@pytest.mark.asyncio
async def test_transcribe_audio_wraps_errors():
    patcher, client = _mock_client()
    client.audio.transcriptions.create = AsyncMock(side_effect=RuntimeError("network down"))
    try:
        with pytest.raises(SpeechServiceError):
            await transcribe_audio(b"fake-bytes")
    finally:
        patcher.stop()


@pytest.mark.asyncio
async def test_synthesize_speech_returns_bytes():
    patcher, client = _mock_client()
    fake_response = MagicMock()
    fake_response.aread = AsyncMock(return_value=b"mp3-bytes-here")
    client.audio.speech.create = AsyncMock(return_value=fake_response)
    try:
        result = await synthesize_speech("Đến giờ uống thuốc rồi bạn ơi.")
    finally:
        patcher.stop()

    assert result == b"mp3-bytes-here"


@pytest.mark.asyncio
async def test_synthesize_speech_wraps_errors():
    patcher, client = _mock_client()
    client.audio.speech.create = AsyncMock(side_effect=RuntimeError("quota exceeded"))
    try:
        with pytest.raises(SpeechServiceError):
            await synthesize_speech("xin chào")
    finally:
        patcher.stop()
