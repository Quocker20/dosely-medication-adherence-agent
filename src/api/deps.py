"""Global FastAPI Dependencies (DB session, current user authentication, RBAC)."""
from src.core.database import get_db
from src.core.security import get_current_user_payload, oauth2_scheme, require_roles

__all__ = ["get_db", "get_current_user_payload", "oauth2_scheme", "require_roles"]
