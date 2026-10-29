from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.core.config import get_settings
from src.core.response import success_response
from src.modules.app_update import service
from src.modules.app_update.schemas import LatestAppVersionResponse

router = APIRouter(prefix="/app", tags=["Application Updates"])


@router.get("/latest-version")
async def get_latest_app_version() -> JSONResponse:
    """Return public metadata for the newest sideloadable Android APK."""
    settings = get_settings()
    filename = service.apk_filename(settings)
    result = LatestAppVersionResponse(
        version_code=settings.android_latest_version_code,
        version_name=settings.android_latest_version_name,
        download_url=service.download_url(settings, filename),
        sha256=await service.apk_sha256(filename),
    )
    return success_response(
        data=result.model_dump(mode="json", by_alias=True),
        message="Latest Android version fetched successfully",
    )
