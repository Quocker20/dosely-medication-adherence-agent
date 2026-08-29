from unittest.mock import patch

import pytest

from src.agents.tool_authorization import ToolAuthorizationError, authorize_patient_write


def test_patient_write_requires_matching_jwt_owner():
    with patch("src.agents.tool_authorization.get_actor_token", return_value="token"), patch(
        "src.agents.tool_authorization.decode_token",
        return_value={"type": "access", "role": "PATIENT", "sub": "p1"},
    ):
        authorize_patient_write("reschedule_remaining_doses", "p1", intent="report_meal_shift")
        with pytest.raises(ToolAuthorizationError):
            authorize_patient_write("reschedule_remaining_doses", "p2", intent="report_meal_shift")


def test_write_tool_rejects_wrong_intent_before_execution():
    with pytest.raises(ToolAuthorizationError):
        authorize_patient_write("reschedule_remaining_doses", "p1", intent="ask_schedule")
