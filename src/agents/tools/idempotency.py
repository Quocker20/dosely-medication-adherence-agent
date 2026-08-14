"""Stable Idempotency-Key derivation for agent write tools.

The backend rejects a write without this header (AdherenceLogService /
AlertService both raise "Idempotency-Key header is required"), so every agent
POST that mutates state has to carry one.

The key is derived, never random. A fresh UUID per call would satisfy the header
check but defeat its purpose: an LLM that retries a tool call would double-log a
dose or page a doctor twice for one symptom — the exact duplicates the backend's
UNIQUE constraint exists to absorb. Deriving from the intent means a retry
produces the same key and replays the original result instead.

Each key carries a coarse time bucket so dedup stays bounded: the same patient
reporting the same symptom again days later must raise a new alert, not be
silently swallowed by a key minted long ago.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone

# Two reports of one symptom inside this window are one clinical event, not two.
_ALERT_BUCKET_SECONDS = 300


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def dose_action_key(scheduled_dose_id: str, action: str, today: date | None = None) -> str:
    """One key per (dose, action, day) — re-reporting "I took it" for the same
    dose on the same day is one fact, however many times it is said."""
    day = (today or datetime.now(timezone.utc).date()).isoformat()
    return _digest("dose_action", scheduled_dose_id, action.upper(), day)


def alert_key(patient_id: str, reason: str, now: datetime | None = None) -> str:
    """One key per (patient, reason, 5-minute bucket)."""
    moment = now or datetime.now(timezone.utc)
    bucket = int(moment.timestamp()) // _ALERT_BUCKET_SECONDS
    return _digest("alert", patient_id, reason, str(bucket))
