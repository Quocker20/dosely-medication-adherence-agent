"""Clinical constants for the patients module."""

from datetime import time

# Seeded for every doctor-created patient so the Planning Agent has anchors to
# work with from the very first approved prescription. Without a routine row,
# expand_schedule raises MissingRoutineAnchorError for any prescribed dose slot
# and the run terminates at NEEDS_REVIEW with zero doses — i.e. a patient with
# a valid prescription and no reminders at all.
#
# These are starting values, not a clinical recommendation: the patient
# replaces them during onboarding. Spacing is what matters here — breakfast to
# lunch is 4h30 and lunch to dinner 6h30, both clear of the default
# min_dose_gap_minutes (240), so a 3-doses-per-day prescription schedules
# cleanly instead of tripping the interval guardrail on day one.
DEFAULT_ROUTINE: dict[str, time] = {
    "wake_time": time(6, 0),
    "breakfast_time": time(7, 0),
    "lunch_time": time(11, 30),
    "dinner_time": time(18, 0),
    "sleep_time": time(22, 0),
}
