import re
from contextvars import ContextVar
from contextvars import Token as ContextToken
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from src.common.exceptions import (
    ForbiddenException,
    UnauthorizedException,
    ValidationException,
)
from src.core.config import get_settings

settings = get_settings()

# OAuth2 bearer scheme pointing to Phone + PIN Password login endpoint
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login", auto_error=False
)

PHONE_REGEX = re.compile(r"^(?:\+84|84|0)[3|5|7|8|9][0-9]{8}$")


def validate_phone_number(phone: str) -> str:
    """Validate and normalize Vietnamese phone numbers to standard format (+84...)."""
    clean_phone = phone.strip().replace(" ", "").replace("-", "")
    if not PHONE_REGEX.match(clean_phone):
        raise ValidationException(
            message="Invalid phone number format. Must be a valid Vietnamese mobile number."
        )

    if clean_phone.startswith("0"):
        clean_phone = "+84" + clean_phone[1:]
    elif clean_phone.startswith("84"):
        clean_phone = "+" + clean_phone
    return clean_phone


def _get_peppered_bytes(plain_password: str, pepper: Optional[str] = None) -> bytes:
    """Combine input password with system pepper into bytes for hashing."""
    pep = pepper if pepper is not None else settings.password_pepper
    return (plain_password + pep).encode("utf-8")


def hash_password(plain_password: str, pepper: Optional[str] = None) -> str:
    """Hash password using bcrypt (with auto-generated unique salt) and global system pepper."""
    peppered_bytes = _get_peppered_bytes(plain_password, pepper)
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(peppered_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(
    plain_password: str, hashed_password: str, pepper: Optional[str] = None
) -> bool:
    """Verify plain password + pepper against stored bcrypt hash."""
    try:
        peppered_bytes = _get_peppered_bytes(plain_password, pepper)
        return bcrypt.checkpw(peppered_bytes, hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(
    user_id: str,
    role: str,
    phone_number: str,
    expires_delta: Optional[timedelta] = None,
    additional_claims: Optional[dict] = None,
) -> str:
    """Generate JWT Access Token for authenticated user."""
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )

    payload = {
        "sub": str(user_id),
        "role": role,
        "phone_number": phone_number,
        "type": "access",
        "iat": now,
        "exp": expire,
    }
    if additional_claims:
        payload.update(additional_claims)

    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def create_refresh_token(
    user_id: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Generate JWT Refresh Token."""
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta or timedelta(days=settings.refresh_token_expire_days)
    )

    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": expire,
    }

    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def decode_token(token: str) -> dict:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise UnauthorizedException(message="Token has expired")
    except jwt.InvalidTokenError:
        raise UnauthorizedException(message="Invalid token signature or payload")


async def get_current_user_payload(
    token: Optional[str] = Depends(oauth2_scheme),
) -> dict:
    """Dependency retrieving and validating token payload."""
    if not token:
        raise UnauthorizedException(message="Missing authentication token")
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise UnauthorizedException(message="Invalid token type")
    return payload


def require_roles(*allowed_roles: str) -> Callable:
    """Dependency factory enforcing Role-Based Access Control (RBAC)."""

    async def role_checker(
        payload: dict = Depends(get_current_user_payload),
    ) -> dict:
        user_role = payload.get("role")
        if user_role not in allowed_roles:
            raise ForbiddenException(
                message=f"Role '{user_role}' is not authorized to access this resource"
            )
        return payload

    return role_checker


# ---------------------------------------------------------------------------
# Actor token propagation
# ---------------------------------------------------------------------------
# The LangGraph agent runs in-process but reaches the backend over HTTP loopback
# (src/modules/planning/core/backend_client.py). Those calls hit the same
# require_roles guards as any client, so they need a real caller identity — a
# static service token would need a role outside ck_users_role and would be able
# to write any patient's data, which is exactly what the HITL boundary forbids.
#
# The caller's own bearer token is therefore carried through a ContextVar rather
# than through AgentState: anything placed in AgentState ends up in the message
# history and in the LLM prompt, where the model could echo it back in a reply.
# A ContextVar keeps the credential out of the model's reach entirely while
# staying automatically scoped to the request task.
_actor_token: ContextVar[Optional[str]] = ContextVar("actor_token", default=None)


def set_actor_token(token: Optional[str]) -> ContextToken:
    """Bind the caller's bearer token for the current async context. Returns a
    reset handle the caller MUST pass to reset_actor_token() when done."""
    return _actor_token.set(token)


def reset_actor_token(handle: ContextToken) -> None:
    """Restore the previous actor token — always call in a finally block so a
    failed turn cannot leak its credential into the next one."""
    _actor_token.reset(handle)


def get_actor_token() -> Optional[str]:
    """Bearer token of the caller whose request is currently being served, or
    None outside a request (e.g. a Celery worker)."""
    return _actor_token.get()
