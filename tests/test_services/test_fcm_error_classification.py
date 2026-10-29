"""O-02: FCM failures are split into transient (retry) and permanent (dead token)."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from firebase_admin import exceptions as fb_exceptions
from firebase_admin import messaging

from src.modules.adherence.fcm_service import FCMService, FCMTransientError


def _resp(exc=None):
    return SimpleNamespace(success=exc is None, exception=exc)


def _batch(*excs):
    responses = [_resp(e) for e in excs]
    return SimpleNamespace(
        responses=responses,
        success_count=sum(1 for r in responses if r.success),
        failure_count=sum(1 for r in responses if not r.success),
    )


def _send(tokens, batch=None, raises=None):
    with patch("src.modules.adherence.fcm_service.messaging.send_each_for_multicast") as send:
        if raises is not None:
            send.side_effect = raises
        else:
            send.return_value = batch
        return FCMService.send_push_notification(tokens=tokens, title="t", body="b")


def test_all_success():
    assert _send(["a", "b"], _batch(None, None)) == (True, [])


def test_unregistered_tokens_are_dead_and_permanent():
    unregistered = messaging.UnregisteredError("gone")
    success, dead = _send(["a", "b"], _batch(unregistered, unregistered))
    assert success is False
    assert dead == ["a", "b"]


def test_partial_success_reports_dead_tokens_without_retry():
    success, dead = _send(["good", "dead"], _batch(None, messaging.UnregisteredError("gone")))
    assert success is True
    assert dead == ["dead"]


@pytest.mark.parametrize(
    "exc",
    [
        fb_exceptions.UnavailableError("503"),
        fb_exceptions.InternalError("500"),
        fb_exceptions.DeadlineExceededError("timeout"),
        messaging.QuotaExceededError("quota"),
    ],
)
def test_transient_per_token_failures_raise_transient_error(exc):
    with pytest.raises(FCMTransientError):
        _send(["a"], _batch(exc))


def test_transient_error_still_carries_the_dead_tokens_found_in_the_same_batch():
    with pytest.raises(FCMTransientError) as info:
        _send(["a", "b"], _batch(messaging.UnregisteredError("gone"), fb_exceptions.UnavailableError("503")))
    assert info.value.dead_tokens == ["a"]


@pytest.mark.parametrize("exc", [fb_exceptions.UnavailableError("503"), ConnectionError("reset"), TimeoutError("slow")])
def test_whole_call_network_failures_raise_transient_error(exc):
    with pytest.raises(FCMTransientError):
        _send(["a"], raises=exc)


def test_whole_call_permanent_failure_is_a_plain_failure_not_a_retry():
    exc = fb_exceptions.UnauthenticatedError("bad credentials")
    assert _send(["a"], raises=exc) == (False, [])
