from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user_payload, get_db
from src.core.rate_limit import rate_limit_by_ip
from src.core.response import success_response
from src.modules.auth.repository import AuthRepository
from src.modules.auth.schemas import (
    ChangePasswordRequest,
    DeviceTokenRequest,
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
)
from src.modules.auth.service import AuthService


def get_auth_service(db: Annotated[AsyncSession, Depends(get_db)]) -> AuthService:
    """Dependency factory providing AuthService instance."""
    repository = AuthRepository(db)
    return AuthService(db=db, repository=repository)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
CurrentUserDep = Annotated[dict, Depends(get_current_user_payload)]

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/login",
    dependencies=[Depends(rate_limit_by_ip("login", 5, 60))],
)
async def login(
    request: LoginRequest,
    service: AuthServiceDep,
) -> JSONResponse:
    """Authenticate user via phone and 6-digit PIN password."""
    result = await service.login(request.phone, request.password)
    return success_response(data=result.model_dump(mode="json"), message="Login successful")


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: CurrentUserDep,
    service: AuthServiceDep,
) -> JSONResponse:
    """Update PIN password. Clears need_onboarding too, but only for
    non-PATIENT roles -- a PATIENT's onboarding gate clears separately once
    they actually finish onboarding."""
    user_id = current_user["sub"]
    result = await service.change_password(
        user_id=user_id,
        current_password=request.current_password,
        new_password=request.new_password,
    )
    return success_response(data=None, message=result.message)


@router.post("/refresh")
async def refresh_token(
    request: RefreshTokenRequest,
    service: AuthServiceDep,
) -> JSONResponse:
    """Exchange valid refresh token for a new token pair."""
    result = await service.refresh_token(request.refresh_token)
    return success_response(data=result.model_dump(mode="json"), message="Token refreshed successfully")


@router.post("/logout")
async def logout(
    request: LogoutRequest,
    current_user: CurrentUserDep,
    service: AuthServiceDep,
) -> JSONResponse:
    """Revoke refresh token session for authenticated user."""
    result = await service.logout(request.refresh_token)
    return success_response(data=None, message=result.message)


@router.post("/device-token")
async def register_device_token(
    request: DeviceTokenRequest,
    current_user: CurrentUserDep,
    service: AuthServiceDep,
) -> JSONResponse:
    """Register or update an FCM token for the authenticated user's device."""
    user_id = current_user["sub"]
    result = await service.register_device_token(
        user_id=user_id,
        fcm_token=request.fcm_token,
        device_name=request.device_name,
    )
    return success_response(data=None, message=result.message)
