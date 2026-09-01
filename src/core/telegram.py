import logging
import uuid
from typing import Any, Dict, List, Optional, Protocol

import httpx

from src.core.config import get_settings

logger = logging.getLogger(__name__)


# ── Exceptions ────────────────────────────────────────────────────────


class TelegramError(Exception):
    """Base exception for Telegram Bot API failures."""


class TelegramBlockedError(TelegramError):
    """HTTP 403: Bot was blocked by the user or kicked from the chat.
    Permanent — never retry, and marks the caregiver link BLOCKED.
    """


class TelegramPermanentError(TelegramError):
    """HTTP 400: Bad request or chat not found.
    Permanent — never retry.
    """


class TelegramRateLimitError(TelegramError):
    """HTTP 429: Too Many Requests.
    Carries the exact retry_after in seconds supplied by Telegram.
    """

    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class TelegramTransientError(TelegramError):
    """HTTP 5xx, network timeout, or connection reset.
    Transient — safe to retry with exponential backoff.
    """


# ── Protocol ──────────────────────────────────────────────────────────


class TelegramClient(Protocol):
    async def send_message(self, chat_id: int, text: str) -> str:
        """Send a plain text message to a Telegram chat. Returns provider message ID."""
        ...


# ── HTTP Implementation ───────────────────────────────────────────────


class HttpTelegramClient:
    """Production client calling the Telegram Bot API over HTTPS."""

    def __init__(
        self,
        token: str,
        base_url: str = "https://api.telegram.org",
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._http_client = http_client

    async def send_message(self, chat_id: int, text: str) -> str:
        endpoint = f"{self._base_url}/bot{self._token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}

        try:
            if self._http_client:
                response = await self._http_client.post(endpoint, json=payload)
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(endpoint, json=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            logger.warning("Telegram network/timeout error sending to chat %s: %s", chat_id, exc)
            raise TelegramTransientError(f"Network error contacting Telegram: {exc}") from exc
        except Exception as exc:
            logger.exception("Unexpected error sending to Telegram chat %s: %s", chat_id, exc)
            raise TelegramTransientError(f"Unexpected transport error: {exc}") from exc

        status_code = response.status_code
        try:
            data = response.json()
        except Exception:
            data = {}

        if status_code == 200 and data.get("ok") is True:
            result = data.get("result", {})
            message_id = result.get("message_id")
            return str(message_id) if message_id is not None else str(uuid.uuid4())

        error_code = data.get("error_code", status_code)
        description = data.get("description", response.text)
        parameters = data.get("parameters", {})

        if error_code == 403 or status_code == 403:
            logger.info("Telegram chat %s blocked the bot (403): %s", chat_id, description)
            raise TelegramBlockedError(f"Telegram blocked: {description}")

        if error_code == 429 or status_code == 429:
            retry_after = int(parameters.get("retry_after", 5))
            logger.warning("Telegram rate limited (429). Retry after %ss", retry_after)
            raise TelegramRateLimitError(f"Rate limited: {description}", retry_after=retry_after)

        if 400 <= status_code < 500:
            logger.warning("Telegram permanent error (%s): %s", error_code, description)
            raise TelegramPermanentError(f"Telegram error {error_code}: {description}")

        logger.warning("Telegram server error (%s): %s", error_code, description)
        raise TelegramTransientError(f"Telegram server error {error_code}: {description}")


# ── Fake Implementation for Tests / Local Dev ─────────────────────────


class FakeTelegramClient:
    """In-memory client for testing and when TELEGRAM_ENABLED is False."""

    def __init__(self) -> None:
        self.sent_messages: List[Dict[str, Any]] = []
        self.error_to_raise: Optional[Exception] = None

    async def send_message(self, chat_id: int, text: str) -> str:
        if self.error_to_raise:
            raise self.error_to_raise

        msg_id = f"fake-msg-{uuid.uuid4().hex[:8]}"
        self.sent_messages.append({"chat_id": chat_id, "text": text, "message_id": msg_id})
        return msg_id

    def clear(self) -> None:
        self.sent_messages.clear()
        self.error_to_raise = None


_fake_instance: Optional[FakeTelegramClient] = None


def get_telegram_client() -> TelegramClient:
    """Factory providing the configured TelegramClient.
    Returns FakeTelegramClient singleton when TELEGRAM_ENABLED is False,
    never attempting network calls with empty credentials.
    """
    global _fake_instance
    settings = get_settings()
    if not settings.telegram_enabled or not settings.telegram_bot_token:
        if _fake_instance is None:
            _fake_instance = FakeTelegramClient()
        return _fake_instance

    return HttpTelegramClient(
        token=settings.telegram_bot_token,
        base_url=settings.telegram_api_base_url,
    )
