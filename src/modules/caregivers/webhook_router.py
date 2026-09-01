import hmac
import logging
from typing import Annotated, Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.core.config import get_settings
from src.core.telegram import TelegramClient, get_telegram_client
from src.modules.caregivers.service import CaregiverService

logger = logging.getLogger(__name__)

webhook_router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def get_caregiver_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    telegram_client: Annotated[TelegramClient, Depends(get_telegram_client)],
) -> CaregiverService:
    return CaregiverService(db, telegram_client=telegram_client)


CaregiverServiceDep = Annotated[CaregiverService, Depends(get_caregiver_service)]


@webhook_router.post("/telegram", status_code=status.HTTP_200_OK)
async def handle_telegram_webhook(
    request: Request,
    service: CaregiverServiceDep,
    x_telegram_bot_api_secret_token: Optional[str] = Header(
        None, alias="X-Telegram-Bot-Api-Secret-Token"
    ),
) -> Dict[str, bool]:
    """Inbound Telegram webhook endpoint. Authenticates header
    `X-Telegram-Bot-Api-Secret-Token` via constant-time comparison against
    configured secret before reading DB. Always returns 200 on well-formed requests.
    """
    settings = get_settings()
    expected_secret = settings.telegram_webhook_secret

    if (
        not expected_secret
        or not x_telegram_bot_api_secret_token
        or not hmac.compare_digest(x_telegram_bot_api_secret_token, expected_secret)
    ):
        logger.warning("Rejected unauthorized Telegram webhook call: secret token mismatch or missing")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing webhook secret token",
        )

    payload: Dict[str, Any] = await request.json()
    await service.handle_webhook_update(payload)
    return {"ok": True}
