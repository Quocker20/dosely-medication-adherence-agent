import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import NoReturn

from sqlalchemy.ext.asyncio import AsyncSession

from src.common.exceptions import (
    ForbiddenException,
    TooManyRequestsException,
    UnauthorizedException,
    ValidationException,
)
from src.core import login_lockout
from src.core.config import get_settings
from src.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password_async,
    verify_password_async,
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
PIN_PATTERN = re.compile(r"^\d{6}$")


def _mask_phone(phone: str) -> str:
    """Keep only the last 3 digits in audit rows."""
    return "*" * max(len(phone) - 3, 0) + phone[-3:]


_dummy_hash_value: str | None = None


async def _dummy_hash() -> str:
    """Valid bcrypt hash used to equalise timing for unknown phone numbers."""
    global _dummy_hash_value
    if _dummy_hash_value is None:
        _dummy_hash_value = await hash_password_async("000000")
    return _dummy_hash_value


class AuthService:
    """Authentication service handling PIN login, password change, and token operations."""

    def __init__(self, db: AsyncSession, repository: AuthRepository) -> None:
        self._db = db
        self._repository = repository

    @staticmethod
    def _is_valid_pin(pin: str) -> bool:
        """Validate if password string is a 6-digit PIN."""
        return bool(pin and PIN_PATTERN.match(pin))

    async def login(
        self, phone: str, password: str, ip_address: str | None = None
    ) -> AuthTokenResponse:
        """Authenticate user with phone and 6-digit PIN password.

        1. Clean phone number to E.164 format.
        2. Retrieve user and verify status.
        3. Verify password + pepper against stored bcrypt hash. Failures (wrong
           PIN or unknown phone, indistinguishable to the caller) count towards
           a per-phone Redis lockout (SEC-03) and are audit-logged without the PIN.
        4. Issue access and refresh tokens.
        5. Return AuthTokenResponse containing must_change_password and
           need_onboarding status.
        """
        try:
            cleaned_phone = clean_phone_number(phone)
        except Exception:
            raise UnauthorizedException(message="Invalid phone number or password")

        remaining = await login_lockout.get_lock_remaining(cleaned_phone)
        if remaining > 0:
            raise TooManyRequestsException(
                message=login_lockout.lock_message(remaining),
                retry_after_seconds=remaining,
            )

        if not self._is_valid_pin(password):
            # Same bcrypt cost as a wrong PIN so timing does not reveal the
            # malformed input; counts as a failure towards the lockout.
            await verify_password_async(password or "", await _dummy_hash())
            await self._login_failed(cleaned_phone, None, "malformed_pin", ip_address)

        # P-03: read, then close the transaction BEFORE the slow bcrypt check so
        # no connection/row state is held while the CPU work runs in a thread.
        async with self._db.begin():
            user = await self._repository.get_user_by_phone(cleaned_phone)

        if user is None or user.status != "ACTIVE":
            # Burn the same bcrypt time so response latency does not reveal
            # whether the phone number exists.
            await verify_password_async(password, await _dummy_hash())
            reason = "unknown_phone" if user is None else "inactive_user"
            await self._login_failed(cleaned_phone, user, reason, ip_address)

        if not await verify_password_async(password, user.hashed_password):
            await self._login_failed(cleaned_phone, user, "wrong_pin", ip_address)

        await login_lockout.reset_failures(cleaned_phone)

        async with self._db.begin():
            # Generate token pair
            access_token = create_access_token(
                user_id=str(user.id),
                role=user.role,
                phone_number=user.phone,
            )
            refresh_token_str = create_refresh_token(user_id=str(user.id))

            token_hash = AuthRepository.hash_token(refresh_token_str)
            refresh_expires_at = datetime.now(UTC) + timedelta(
                days=settings.refresh_token_expire_days
            )
            await self._repository.save_refresh_token(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=refresh_expires_at,
            )
            await self._repository.update_last_login(user.id)

        return AuthTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token_str,
            token_type="Bearer",
            expires_in=settings.access_token_expire_minutes * 60,
            must_change_password=user.password_changed_at is None,
            need_onboarding=user.need_onboarding,
            user=UserResponse(
                id=user.id,
                phone=user.phone,
                role=user.role,
                status=user.status,
            ),
        )

    async def _login_failed(
        self,
        cleaned_phone: str,
        user,
        reason: str,
        ip_address: str | None,
    ) -> NoReturn:
        """Count the failure, audit-log it (never the PIN) and raise.

        Always raises: 429 if this failure tripped the lockout, otherwise the
        same generic 401 for unknown phone / inactive / wrong PIN.
        """
        # Local import: admin.repository imports auth models, so a top-level
        # import here is circular when alembic/env.py loads the model registry.
        from src.modules.admin.repository import AuditLogRepository

        locked_for = await login_lockout.register_failure(cleaned_phone)
        try:
            async with self._db.begin():
                await AuditLogRepository(self._db).create_audit_log(
                    action="LOGIN_FAILED",
                    entity_type="auth",
                    actor_user_id=user.id if user is not None else None,
                    entity_id=user.id if user is not None else None,
                    new_values={
                        "phone": _mask_phone(cleaned_phone),
                        "reason": reason,
                        "locked_for_seconds": locked_for or None,
                    },
                    ip_address=ip_address,
                )
        except Exception:  # noqa: BLE001 - auditing must not change the response
            logger.warning("Could not audit-log failed login", exc_info=True)
        if locked_for:
            raise TooManyRequestsException(
                message=login_lockout.lock_message(locked_for),
                retry_after_seconds=locked_for,
            )
        raise UnauthorizedException(message="Invalid phone number or password")

    async def change_password(
        self, user_id: str | uuid.UUID, current_password: str, new_password: str
    ) -> MessageResponse:
        """Change user password PIN and record password_changed_at.

        1. Retrieve user by ID.
        2. Verify current password.
        3. Validate new_password format (must be 6-digit PIN).
        4. Hash new password with bcrypt + pepper.
        5. Update password + password_changed_at in database.
        6. Clear need_onboarding too, but only for non-PATIENT roles -- a
           PATIENT's onboarding gate is separate from their PIN-change gate
           and only clears once they actually finish onboarding.
        7. Revoke existing refresh tokens.
        """
        if not self._is_valid_pin(new_password):
            raise ValidationException(message="New password must be a 6-digit PIN")

        uid = uuid.UUID(str(user_id)) if isinstance(user_id, str) else user_id

        # P-03: bcrypt runs in worker threads with no transaction open.
        async with self._db.begin():
            user = await self._repository.get_user_by_id(uid)
        if user is None:
            raise UnauthorizedException(message="User not found")

        if not await verify_password_async(current_password, user.hashed_password):
            raise ValidationException(message="Current password is incorrect")

        new_hashed = await hash_password_async(new_password)
        async with self._db.begin():
            await self._repository.change_password(
                user.id, new_hashed, clear_need_onboarding=user.role != "PATIENT"
            )

        return MessageResponse(message="Password changed successfully")

    async def refresh_token(self, refresh_token_str: str) -> AuthTokenResponse:
        """Exchange a refresh token for a new pair, rotating it (SEC-19).

        * Normal: old token revoked (marked rotated), new token in the same family.
        * Reuse of an already-rotated token:
            - within ``refresh_reuse_grace_seconds`` of the rotation: treated as
              a client retry after a lost response. A fresh pair is issued in
              the same family and nothing is revoked (the earlier replacement
              stays valid for that short window too).
            - later: possible theft -> the whole family (session) is revoked
              and the caller gets 401.
        * The token row is locked (FOR UPDATE) so concurrent refreshes with the
          same token serialise; the loser lands in the grace branch.
        """
        payload = decode_token(refresh_token_str)
        if payload.get("type") != "refresh":
            raise UnauthorizedException(message="Invalid token type")

        token_hash = AuthRepository.hash_token(refresh_token_str)
        grace = timedelta(seconds=settings.refresh_reuse_grace_seconds)
        reuse_detected = False
        result: AuthTokenResponse | None = None

        async with self._db.begin():
            stored = await self._repository.get_refresh_token_for_update(token_hash)
            now = datetime.now(UTC)
            if stored is None or str(stored.user_id) != payload.get("sub"):
                raise UnauthorizedException(
                    message="Refresh token not found or already revoked"
                )
            if stored.expires_at < now:
                raise UnauthorizedException(message="Refresh token has expired")

            in_grace = False
            if stored.revoked_at is not None:
                if stored.rotated_at is None:
                    # Revoked by logout / PIN change: plain rejection.
                    raise UnauthorizedException(
                        message="Refresh token not found or already revoked"
                    )
                if now - stored.rotated_at <= grace:
                    in_grace = True
                else:
                    reuse_detected = True
                    await self._repository.revoke_family(stored.family_id)

            if not reuse_detected:
                user = await self._repository.get_user_by_id(stored.user_id)
                if user is None or user.status != "ACTIVE":
                    raise UnauthorizedException(message="User not found or inactive")

                new_access_token = create_access_token(
                    user_id=str(user.id),
                    role=user.role,
                    phone_number=user.phone,
                )
                new_refresh_token = create_refresh_token(user_id=str(user.id))
                new_record = await self._repository.save_refresh_token(
                    user_id=user.id,
                    token_hash=AuthRepository.hash_token(new_refresh_token),
                    expires_at=now
                    + timedelta(days=settings.refresh_token_expire_days),
                    family_id=stored.family_id,
                )
                if not in_grace:
                    await self._repository.mark_rotated(stored.id, new_record.id, now)

                result = AuthTokenResponse(
                    access_token=new_access_token,
                    refresh_token=new_refresh_token,
                    token_type="Bearer",
                    expires_in=settings.access_token_expire_minutes * 60,
                    must_change_password=user.password_changed_at is None,
                    need_onboarding=user.need_onboarding,
                    user=UserResponse(
                        id=user.id,
                        phone=user.phone,
                        role=user.role,
                        status=user.status,
                    ),
                )

        # Raised after the transaction block so the family revocation commits.
        if reuse_detected or result is None:
            logger.warning("Refresh token reuse detected; session revoked")
            raise UnauthorizedException(
                message="Refresh token reuse detected. Please log in again."
            )
        return result

    async def logout(
        self,
        refresh_token_str: str,
        current_user_id: str | uuid.UUID,
        fcm_token: str | None = None,
    ) -> MessageResponse:
        """Revoke the caller's own refresh token on logout.

        SEC-05: the token must belong to the authenticated user; otherwise 403
        and nothing is revoked, so one user cannot log another out by
        presenting their refresh token. An unknown token is a no-op success
        (logout is idempotent and must not reveal which tokens exist).
        """
        uid = (
            uuid.UUID(str(current_user_id))
            if not isinstance(current_user_id, uuid.UUID)
            else current_user_id
        )
        token_hash = AuthRepository.hash_token(refresh_token_str)
        async with self._db.begin():
            stored = await self._repository.get_refresh_token_any_state(token_hash)
            if stored is not None and stored.user_id != uid:
                raise ForbiddenException(
                    message="Refresh token does not belong to the current user"
                )
            if stored is not None:
                # Whole session: grace-path refreshes can leave several live
                # tokens in one family.
                await self._repository.revoke_family(stored.family_id)
            if fcm_token:
                # SEC-20: this device must stop receiving the user's pushes.
                await self._repository.deactivate_user_device(uid, fcm_token)
        return MessageResponse(message="Logged out successfully")

    async def register_device_token(
        self, user_id: str | uuid.UUID, fcm_token: str, device_name: str | None = None
    ) -> MessageResponse:
        """Register or update an FCM token for the user."""
        uid = uuid.UUID(str(user_id)) if isinstance(user_id, str) else user_id
        async with self._db.begin():
            await self._repository.upsert_user_device(uid, fcm_token, device_name)
        return MessageResponse(message="Device token registered successfully")
