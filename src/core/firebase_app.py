import logging
import os

import firebase_admin
from firebase_admin import credentials

from src.core.config import get_settings

logger = logging.getLogger(__name__)


def init_firebase() -> None:
    settings = get_settings()
    key_path = settings.firebase_service_account_key_path

    if not os.path.exists(key_path):
        logger.warning(
            f"Firebase Service Account Key not found at {key_path}. "
            f"FCM Notifications will not be delivered."
        )
        return

    try:
        # Check if already initialized (for tests/reloads)
        firebase_admin.get_app()
        logger.info("Firebase Admin already initialized.")
    except ValueError:
        try:
            cred = credentials.Certificate(key_path)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Firebase Admin: {e}")
