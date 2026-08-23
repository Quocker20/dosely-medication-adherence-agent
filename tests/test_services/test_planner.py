import uuid
from datetime import date
from decimal import Decimal

import pytest

from src.modules.agents.planner import FrequencyGuardrailError, PlannableItem, validate_frequency_guardrails


def _item(**overrides) -> PlannableItem:
    defaults = dict(
        id=uuid.uuid4(),
        medication_id=uuid.uuid4(),
        dose_unit="tablet",
        morning_dose=Decimal("1"),
        noon_dose=None,
        evening_dose=Decimal("1"),
        bedtime_dose=None,
        meal_relation="AFTER_MEAL",
        minimum_interval_minutes=None,
        start_date=date(2026, 8, 14),
        end_date=None,
    )
    defaults.update(overrides)
    return PlannableItem(**defaults)


class TestValidateFrequencyGuardrails:
    def test_passes_at_exactly_max_per_day(self):
        item = _item(
            morning_dose=Decimal("1"),
            noon_dose=Decimal("1"),
            evening_dose=Decimal("1"),
            bedtime_dose=Decimal("1"),
        )
        validate_frequency_guardrails([item], max_per_day=4)  # no raise

    def test_raises_above_max_per_day(self):
        item = _item(
            morning_dose=Decimal("1"),
            noon_dose=Decimal("1"),
            evening_dose=Decimal("1"),
            bedtime_dose=Decimal("1"),
        )
        with pytest.raises(FrequencyGuardrailError):
            validate_frequency_guardrails([item], max_per_day=3)

    def test_ignores_none_and_zero_dose_fields(self):
        item = _item(
            morning_dose=Decimal("0"),
            noon_dose=None,
            evening_dose=Decimal("1"),
            bedtime_dose=None,
        )
        validate_frequency_guardrails([item], max_per_day=1)  # no raise

    def test_error_message_names_the_item(self):
        item = _item(
            morning_dose=Decimal("1"),
            noon_dose=Decimal("1"),
            evening_dose=Decimal("1"),
            bedtime_dose=Decimal("1"),
        )
        with pytest.raises(FrequencyGuardrailError) as exc_info:
            validate_frequency_guardrails([item], max_per_day=2)
        assert str(item.id) in str(exc_info.value)
