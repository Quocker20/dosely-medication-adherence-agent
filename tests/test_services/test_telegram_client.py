import pytest
import httpx

from src.core.telegram import (
    FakeTelegramClient,
    HttpTelegramClient,
    TelegramBlockedError,
    TelegramRateLimitError,
    TelegramTransientError,
)


@pytest.mark.asyncio
async def test_fake_telegram_client_records_messages():
    client = FakeTelegramClient()
    msg_id = await client.send_message(chat_id=123456789, text="Hello caregiver")
    assert msg_id.startswith("fake-msg-")
    assert len(client.sent_messages) == 1
    assert client.sent_messages[0]["chat_id"] == 123456789
    assert client.sent_messages[0]["text"] == "Hello caregiver"


@pytest.mark.asyncio
async def test_fake_telegram_client_raises_injected_error():
    client = FakeTelegramClient()
    client.error_to_raise = TelegramBlockedError("User blocked bot")
    with pytest.raises(TelegramBlockedError):
        await client.send_message(chat_id=123456789, text="Hello")


@pytest.mark.asyncio
async def test_http_telegram_client_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 9999}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = HttpTelegramClient(token="fake_token", base_url="https://api.telegram.org", http_client=http_client)
        msg_id = await client.send_message(chat_id=123456789, text="Test message")
        assert msg_id == "9999"


@pytest.mark.asyncio
async def test_http_telegram_client_403_blocked():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403, json={"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"}
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = HttpTelegramClient(token="fake_token", base_url="https://api.telegram.org", http_client=http_client)
        with pytest.raises(TelegramBlockedError):
            await client.send_message(chat_id=123456789, text="Test")


@pytest.mark.asyncio
async def test_http_telegram_client_429_rate_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "ok": False,
                "error_code": 429,
                "description": "Too Many Requests: retry after 12",
                "parameters": {"retry_after": 12},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = HttpTelegramClient(token="fake_token", base_url="https://api.telegram.org", http_client=http_client)
        with pytest.raises(TelegramRateLimitError) as exc_info:
            await client.send_message(chat_id=123456789, text="Test")
        assert exc_info.value.retry_after == 12


@pytest.mark.asyncio
async def test_http_telegram_client_500_transient():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500, json={"ok": False, "error_code": 500, "description": "Internal server error"}
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = HttpTelegramClient(token="fake_token", base_url="https://api.telegram.org", http_client=http_client)
        with pytest.raises(TelegramTransientError):
            await client.send_message(chat_id=123456789, text="Test")
