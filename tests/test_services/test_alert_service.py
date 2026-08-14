"""SOS/alert creation: the trigger source and severity must reach the columns.

The endpoint is shared by two callers — the patient's SOS button and the agent
after it detects a severe symptom in chat. Both were being written as
triggered_by_type='SOS_BUTTON'/severity='CRITICAL', so the doctor's dashboard
could not tell them apart and `GET /alerts` could not filter on either.
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.adherence.schemas import TriggerSosRequest
from src.modules.adherence.service import AlertService

PATIENT_ID = uuid.uuid4()


class TestTriggerSosRequestDefaults:
    def test_defaults_preserve_the_button_press_case(self):
        """An existing client sends neither field and must keep its behaviour."""
        request = TriggerSosRequest(message="cứu tôi")
        assert request.triggered_by_type == "SOS_BUTTON"
        assert request.severity == "CRITICAL"

    def test_accepts_the_agent_detection_case(self):
        request = TriggerSosRequest(
            message="[HIGH] SEVERE_SYMPTOM: tức ngực",
            triggered_by_type="SEVERE_SYMPTOM",
            severity="HIGH",
        )
        assert request.triggered_by_type == "SEVERE_SYMPTOM"
        assert request.severity == "HIGH"

    @pytest.mark.parametrize(
        "field,value",
        [
            ("triggered_by_type", "SOMETHING_ELSE"),
            ("severity", "LOW"),
        ],
    )
    def test_rejects_values_the_db_constraint_would_reject(self, field, value):
        """ck_alerts_triggered_by_type / ck_alerts_severity (migration 0009) —
        catching it here turns a lost alert into a 422."""
        with pytest.raises(ValueError):
            TriggerSosRequest(**{field: value})


def _fake_alert(**overrides):
    base = dict(
        id=uuid.uuid4(),
        patient_id=PATIENT_ID,
        assigned_doctor_id=None,
        triggered_by_type="SOS_BUTTON",
        alert_type="RED_ALERT",
        severity="CRITICAL",
        status="OPEN",
        message=None,
        created_at=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _service_with_mocks():
    db = MagicMock()
    db.in_transaction.return_value = False
    begin_ctx = MagicMock()
    begin_ctx.__aenter__ = AsyncMock(return_value=None)
    begin_ctx.__aexit__ = AsyncMock(return_value=False)
    db.begin.return_value = begin_ctx

    alert_repo = AsyncMock()
    patient_repo = AsyncMock()
    patient_repo.get_patient_with_user.return_value = SimpleNamespace(user_id=PATIENT_ID)

    service = AlertService(
        db=db,
        alert_repository=alert_repo,
        audit_repository=AsyncMock(),
        patient_repository=patient_repo,
    )
    return service, alert_repo


@pytest.mark.asyncio
async def test_agent_detected_alert_keeps_its_own_trigger_type_and_severity():
    service, alert_repo = _service_with_mocks()
    alert_repo.create_alert.return_value = _fake_alert(
        triggered_by_type="SEVERE_SYMPTOM", severity="HIGH"
    )

    await service.trigger_sos(
        patient_id=PATIENT_ID,
        request=TriggerSosRequest(
            message="[HIGH] SEVERE_SYMPTOM: tức ngực",
            triggered_by_type="SEVERE_SYMPTOM",
            severity="HIGH",
        ),
        actor_payload={"sub": str(PATIENT_ID)},
        idempotency_key="key-1",
    )

    kwargs = alert_repo.create_alert.call_args.kwargs
    assert kwargs["triggered_by_type"] == "SEVERE_SYMPTOM"
    assert kwargs["severity"] == "HIGH"
    assert kwargs["alert_type"] == "RED_ALERT"


@pytest.mark.asyncio
async def test_plain_sos_still_writes_a_critical_button_press():
    service, alert_repo = _service_with_mocks()
    alert_repo.create_alert.return_value = _fake_alert()

    await service.trigger_sos(
        patient_id=PATIENT_ID,
        request=TriggerSosRequest(message="cứu tôi"),
        actor_payload={"sub": str(PATIENT_ID)},
        idempotency_key="key-2",
    )

    kwargs = alert_repo.create_alert.call_args.kwargs
    assert kwargs["triggered_by_type"] == "SOS_BUTTON"
    assert kwargs["severity"] == "CRITICAL"
