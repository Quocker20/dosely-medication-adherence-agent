"""Deterministic patient addressing derived from the authenticated profile."""

from __future__ import annotations

from datetime import date

from src.modules.planning.core.backend_client import BackendAPIError, get

DEFAULT_PATIENT_ADDRESS = "bạn"


def resolve_patient_address(profile: object, reference_date: date) -> str:
    """Return bác/anh/chị/bạn without asking an LLM to infer demographics."""
    if not isinstance(profile, dict):
        return DEFAULT_PATIENT_ADDRESS
    try:
        dob = date.fromisoformat(str(profile.get("dob") or ""))
    except ValueError:
        return DEFAULT_PATIENT_ADDRESS

    age = reference_date.year - dob.year - ((reference_date.month, reference_date.day) < (dob.month, dob.day))
    if age < 0:
        return DEFAULT_PATIENT_ADDRESS
    if age >= 60:
        return "bác"
    if age < 18:
        return DEFAULT_PATIENT_ADDRESS

    sex = str(profile.get("sex") or "").upper()
    if sex == "MALE":
        return "anh"
    if sex == "FEMALE":
        return "chị"
    return DEFAULT_PATIENT_ADDRESS


async def get_patient_address(patient_id: str, reference_date: date | None = None) -> str:
    """Fetch the authenticated profile once and safely derive its vocative."""
    try:
        payload = await get("/patients/me/profile")
    except BackendAPIError:
        return DEFAULT_PATIENT_ADDRESS
    if not isinstance(payload, dict):
        return DEFAULT_PATIENT_ADDRESS
    profile = payload.get("profile")
    if not isinstance(profile, dict):
        return DEFAULT_PATIENT_ADDRESS
    actual_patient_id = str(profile.get("user_id") or "")
    if actual_patient_id and actual_patient_id != patient_id:
        return DEFAULT_PATIENT_ADDRESS
    return resolve_patient_address(profile, reference_date or date.today())
