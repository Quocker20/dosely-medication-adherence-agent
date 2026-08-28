import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.modules.auth.models import RefreshToken, User, UserDevice

logger = logging.getLogger(__name__)


class AuthRepository:
    """Repository handling User and RefreshToken database operations."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── SQL: User operations ──

    async def get_user_by_phone(self, phone: str) -> Optional[User]:
        """Fetch user by phone number."""
        stmt = select(User).where(User.phone == phone)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        """Fetch user by ID."""
        stmt = select(User).where(User.id == user_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_user(
        self, phone: str, hashed_password: str, role: str = "PATIENT"
    ) -> User:
        """Create new user with phone, hashed_password, and default role."""
        user = User(
            id=uuid.uuid4(),
            phone=phone,
            hashed_password=hashed_password,
            role=role,
            need_onboarding=True,
            status="ACTIVE",
        )
        self._db.add(user)
        await self._db.flush()
        return user

    async def change_password(
        self, user_id: uuid.UUID, hashed_password: str, clear_need_onboarding: bool
    ) -> None:
        """Atomically update password, record password_changed_at, optionally
        clear need_onboarding, and revoke all active refresh tokens.

        clear_need_onboarding is only True for non-PATIENT roles (DOCTOR,
        ADMIN, CAREGIVER): their temp-PIN change IS their whole onboarding
        gate. A PATIENT's need_onboarding stays True here -- it only clears
        when they actually finish onboarding (see PatientService), so closing
        the app between changing the PIN and finishing onboarding still routes
        them back to it on the next launch.
        """
        now = datetime.now(timezone.utc)
        values: dict = {
            "hashed_password": hashed_password,
            "password_changed_at": now,
            "updated_at": now,
        }
        if clear_need_onboarding:
            values["need_onboarding"] = False
        stmt_user = update(User).where(User.id == user_id).values(**values)
        stmt_tokens = (
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await self._db.execute(stmt_user)
        await self._db.execute(stmt_tokens)

    async def clear_need_onboarding(self, user_id: uuid.UUID) -> None:
        """Mark a patient as having finished onboarding.

        The `need_onboarding` predicate makes a repeat call (double-submit,
        or onboarding finished via two different endpoints) a zero-row no-op
        instead of a redundant write.
        """
        stmt = (
            update(User)
            .where(User.id == user_id, User.need_onboarding.is_(True))
            .values(need_onboarding=False, updated_at=datetime.now(timezone.utc))
        )
        await self._db.execute(stmt)

    async def update_last_login(self, user_id: uuid.UUID) -> None:
        """Update user last_login_at timestamp."""
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(last_login_at=datetime.now(timezone.utc))
        )
        await self._db.execute(stmt)

    async def update_user_status(self, user_id: uuid.UUID, status: str) -> None:
        """Update user account status."""
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(status=status, updated_at=datetime.now(timezone.utc))
        )
        await self._db.execute(stmt)

    async def upsert_user_device(
        self, user_id: uuid.UUID, fcm_token: str, device_name: Optional[str] = None
    ) -> None:
        """Upsert an FCM token for the user. If token already exists (for any user), 
        reassign it to the current user and update device_name/active status."""
        stmt = (
            pg_insert(UserDevice)
            .values(
                user_id=user_id,
                fcm_token=fcm_token,
                device_name=device_name,
                is_active=True,
            )
            .on_conflict_do_update(
                index_elements=["fcm_token"],
                set_={
                    "user_id": user_id,
                    "device_name": device_name,
                    "is_active": True,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
        )
        await self._db.execute(stmt)

    # ── SQL: RefreshToken operations ──

    async def save_refresh_token(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        device_info: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> RefreshToken:
        """Persist a new refresh token record."""
        record = RefreshToken(
            id=uuid.uuid4(),
            user_id=user_id,
            token_hash=token_hash,
            device_info=device_info,
            ip_address=ip_address,
            expires_at=expires_at,
        )
        self._db.add(record)
        await self._db.flush()
        return record

    async def get_refresh_token_by_hash(
        self, token_hash: str
    ) -> Optional[RefreshToken]:
        """Find active (non-revoked) refresh token by hash."""
        stmt = select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke_refresh_token(self, token_hash: str) -> None:
        """Revoke a single refresh token by hash."""
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await self._db.execute(stmt)

    async def revoke_all_user_tokens(self, user_id: uuid.UUID) -> None:
        """Revoke all active refresh tokens for a user."""
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await self._db.execute(stmt)

    # ── Utility ──

    @staticmethod
    def hash_token(token: str) -> str:
        """SHA-256 hash a token string for secure storage."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
