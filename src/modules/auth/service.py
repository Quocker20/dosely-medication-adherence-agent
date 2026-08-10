import logging
import uuid
from datetime import datetime, timedelta, timezone

from src.common.exceptions import UnauthorizedException, ValidationException
from src.core.config import get_settings
from src.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from src.core.utils import clean_phone_number
from src.modules.auth.repository import AuthRepository
from src.modules.auth.schemas import (
    AuthTokenResponse,
    MessageResponse,
    UserResponse,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class AuthService:
    """Authentication service handling PIN login, password change, and token operations."""

    def __init__(self, repository: AuthRepository) -> None:
        self._repository = repository

    async def login(self, phone: str, password: str) -> AuthTokenResponse:
        """Authenticate user with phone and 6-digit PIN password.

        1. Clean phone number to E.164 format.
        2. Retrieve user and verify status.
        3. Verify password + pepper against stored bcrypt hash.
        4. Issue access and refresh tokens.
        5. Return AuthTokenResponse containing is_first_login status.
        """
        import re
        if not re.match(r"^\d{6}$", password):
            raise UnauthorizedException(message="Invalid phone number or password")

        try:
            cleaned_phone = clean_phone_number(phone)
        except Exception:
            raise UnauthorizedException(message="Invalid phone number or password")

        user = await self._repository.get_user_by_phone(cleaned_phone)
        if user is None or user.status != "ACTIVE":
            raise UnauthorizedException(message="Invalid phone number or password")

        if not verify_password(password, user.hashed_password):
            raise UnauthorizedException(message="Invalid phone number or password")

        # Generate token pair
        access_token = create_access_token(
            user_id=str(user.id),
            role=user.role,
            phone_number=user.phone,
        )
        refresh_token_str = create_refresh_token(user_id=str(user.id))

        # Persist hashed refresh token
        token_hash = AuthRepository.hash_token(refresh_token_str)
        refresh_expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.refresh_token_expire_days
        )
        await self._repository.save_refresh_token(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=refresh_expires_at,
        )

        # Update last login timestamp
        await self._repository.update_last_login(user.id)

        return AuthTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token_str,
            token_type="Bearer",
            expires_in=settings.access_token_expire_minutes * 60,
            is_first_login=user.is_first_login,
            user=UserResponse(
                id=user.id,
                phone=user.phone,
                role=user.role,
                status=user.status,
            ),
        )

    async def change_password(
        self, user_id: str | uuid.UUID, current_password: str, new_password: str
    ) -> MessageResponse:
        """Change user password PIN and mark is_first_login as False.

        1. Retrieve user by ID.
        2. Verify current password.
        3. Hash new password with bcrypt + pepper.
        4. Update password in database.
        5. Set is_first_login = False.
        6. Revoke existing refresh tokens.
        """
        uid = uuid.UUID(str(user_id)) if isinstance(user_id, str) else user_id
        user = await self._repository.get_user_by_id(uid)
        if user is None:
            raise UnauthorizedException(message="User not found")

        if not verify_password(current_password, user.hashed_password):
            raise ValidationException(message="Current password is incorrect")

        new_hashed = hash_password(new_password)
        await self._repository.change_password(user.id, new_hashed)

        return MessageResponse(message="Password changed successfully")

    async def refresh_token(self, refresh_token_str: str) -> AuthTokenResponse:
        """Exchange valid refresh token for a new token pair."""
        payload = decode_token(refresh_token_str)
        if payload.get("type") != "refresh":
            raise UnauthorizedException(message="Invalid token type")

        token_hash = AuthRepository.hash_token(refresh_token_str)
        stored_token = await self._repository.get_refresh_token_by_hash(token_hash)
        if stored_token is None:
            raise UnauthorizedException(
                message="Refresh token not found or already revoked"
            )

        if stored_token.expires_at < datetime.now(timezone.utc):
            raise UnauthorizedException(message="Refresh token has expired")

        # Revoke old refresh token
        await self._repository.revoke_refresh_token(token_hash)

        # Fetch user for new token claims
        user_id = uuid.UUID(payload["sub"])
        user = await self._repository.get_user_by_id(user_id)
        if user is None or user.status != "ACTIVE":
            raise UnauthorizedException(message="User not found or inactive")

        # Generate new token pair
        new_access_token = create_access_token(
            user_id=str(user.id),
            role=user.role,
            phone_number=user.phone,
        )
        new_refresh_token = create_refresh_token(user_id=str(user.id))

        # Persist new refresh token
        new_token_hash = AuthRepository.hash_token(new_refresh_token)
        new_expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.refresh_token_expire_days
        )
        await self._repository.save_refresh_token(
            user_id=user.id,
            token_hash=new_token_hash,
            expires_at=new_expires_at,
        )

        return AuthTokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="Bearer",
            expires_in=settings.access_token_expire_minutes * 60,
            is_first_login=user.is_first_login,
            user=UserResponse(
                id=user.id,
                phone=user.phone,
                role=user.role,
                status=user.status,
            ),
        )

    async def logout(self, refresh_token_str: str) -> MessageResponse:
        """Revoke refresh token on logout."""
        token_hash = AuthRepository.hash_token(refresh_token_str)
        await self._repository.revoke_refresh_token(token_hash)
        return MessageResponse(message="Logged out successfully")
