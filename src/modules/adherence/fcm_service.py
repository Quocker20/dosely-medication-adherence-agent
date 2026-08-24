import logging
from typing import Any, Dict, List, Optional, Tuple

from firebase_admin import messaging

logger = logging.getLogger(__name__)


class FCMService:
    """Service to handle Firebase Cloud Messaging pushing."""

    @staticmethod
    def send_push_notification(
        tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[str]]:
        """
        Send a multicast push notification via FCM.
        Returns:
            (success: bool, dead_tokens: List[str])
            success: True if at least one message was successfully delivered.
            dead_tokens: List of unregistered/invalid tokens that should be deactivated in DB.
        """
        if not tokens:
            logger.warning("No FCM tokens provided to send_push_notification.")
            return False, []

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

        dead_tokens: List[str] = []
        try:
            response = messaging.send_each_for_multicast(message)
            logger.info(
                f"FCM Multicast response: {response.success_count} successes, {response.failure_count} failures."
            )

            if response.failure_count > 0:
                for idx, resp in enumerate(response.responses):
                    if not resp.success:
                        logger.warning(
                            f"Failed to send to token {tokens[idx][:10]}...: {resp.exception}"
                        )
                        if isinstance(
                            resp.exception,
                            (
                                messaging.UnregisteredError,
                                messaging.SenderIdMismatchError,
                            ),
                        ) or "registration-token-not-registered" in str(resp.exception).lower():
                            dead_tokens.append(tokens[idx])

            return response.success_count > 0, dead_tokens
        except Exception as e:
            logger.error(f"Error sending FCM message: {e}")
            return False, []
