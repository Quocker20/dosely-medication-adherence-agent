import logging
from typing import Any

from firebase_admin import exceptions as fb_exceptions
from firebase_admin import messaging

logger = logging.getLogger(__name__)

# Errors worth retrying: the push may well succeed a few seconds later.
# QuotaExceededError subclasses ResourceExhaustedError.
_TRANSIENT_FIREBASE_ERRORS = (
    fb_exceptions.UnavailableError,
    fb_exceptions.InternalError,
    fb_exceptions.DeadlineExceededError,
    fb_exceptions.ResourceExhaustedError,
)
_TRANSIENT_NETWORK_ERRORS = (ConnectionError, TimeoutError)


class FCMTransientError(Exception):
    """FCM could not deliver to any device because of a temporary problem
    (network, 5xx/UNAVAILABLE/INTERNAL, quota). The caller retries with backoff.

    dead_tokens carries tokens found unregistered in the same batch so they
    are still deactivated even though the delivery is going to be retried.
    """

    def __init__(self, message: str, dead_tokens: list[str] | None = None) -> None:
        super().__init__(message)
        self.dead_tokens: list[str] = dead_tokens or []


def _is_transient(exc: BaseException | None) -> bool:
    return isinstance(exc, _TRANSIENT_FIREBASE_ERRORS + _TRANSIENT_NETWORK_ERRORS)


class FCMService:
    """Service to handle Firebase Cloud Messaging pushing."""

    @staticmethod
    def send_push_notification(
        tokens: list[str],
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> tuple[bool, list[str]]:
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

        dead_tokens: list[str] = []
        try:
            response = messaging.send_each_for_multicast(message)
        except Exception as exc:
            if _is_transient(exc):
                raise FCMTransientError(f"FCM call failed transiently: {type(exc).__name__}") from exc
            logger.error("FCM call failed permanently (%s)", type(exc).__name__, exc_info=True)
            return False, []

        logger.info(
            "FCM multicast response: %d successes, %d failures.", response.success_count, response.failure_count
        )
        transient_failures = 0
        for idx, resp in enumerate(response.responses):
            if resp.success:
                continue
            # Log the exception class, never the token or message payload.
            logger.warning("FCM send to token %s... failed: %s", tokens[idx][:6], type(resp.exception).__name__)
            if isinstance(
                resp.exception,
                (messaging.UnregisteredError, messaging.SenderIdMismatchError),
            ) or "registration-token-not-registered" in str(resp.exception).lower():
                dead_tokens.append(tokens[idx])
            elif _is_transient(resp.exception):
                transient_failures += 1

        if response.success_count > 0:
            # At least one device got it: retrying would push a duplicate to them.
            return True, dead_tokens
        if transient_failures > 0:
            raise FCMTransientError(
                f"FCM failed transiently for {transient_failures} of {len(tokens)} token(s)",
                dead_tokens=dead_tokens,
            )
        return False, dead_tokens
