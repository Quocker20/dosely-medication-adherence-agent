import logging
from typing import Dict, List, Any

from firebase_admin import messaging

logger = logging.getLogger(__name__)


class FCMService:
    """Service to handle Firebase Cloud Messaging pushing."""

    @staticmethod
    def send_push_notification(
        tokens: List[str],
        title: str,
        body: str,
        data: Dict[str, Any] = None,
    ) -> bool:
        """
        Send a multicast push notification via FCM.
        Returns True if at least one message was successfully handed off to FCM,
        False if there was a failure for all tokens or no tokens provided.
        """
        if not tokens:
            logger.warning("No FCM tokens provided to send_push_notification.")
            return False

        # Convert data dict values to string (FCM requires string values in data payload)
        fcm_data = {}
        if data:
            for k, v in data.items():
                if isinstance(v, (dict, list)):
                    import json
                    fcm_data[k] = json.dumps(v)
                else:
                    fcm_data[k] = str(v)

        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=fcm_data,
            tokens=tokens,
        )

        try:
            response = messaging.send_each_for_multicast(message)
            logger.info(f"FCM Multicast response: {response.success_count} successes, {response.failure_count} failures.")
            
            # Optionally: Handle failed tokens (e.g. Unregistered) to clean up DB
            # We would return the failed tokens so the caller can delete them.
            if response.failure_count > 0:
                for idx, resp in enumerate(response.responses):
                    if not resp.success:
                        # e.g., messaging.UnregisteredError implies token is dead
                        logger.warning(f"Failed to send to token {tokens[idx][:10]}...: {resp.exception}")

            return response.success_count > 0
        except Exception as e:
            logger.error(f"Error sending FCM message: {e}")
            return False
