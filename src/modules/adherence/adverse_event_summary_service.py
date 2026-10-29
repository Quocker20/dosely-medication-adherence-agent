"""Daily roll-up of low/moderate suspected adverse events into one alert per patient."""

import uuid
from datetime import datetime, timedelta

from src.modules.adherence.models import SuspectedAdverseEvent
from src.modules.adherence.repository import AlertRepository, SuspectedAdverseEventRepository


def group_events_by_patient(
    events: list[SuspectedAdverseEvent],
) -> dict[uuid.UUID, list[SuspectedAdverseEvent]]:
    grouped: dict[uuid.UUID, list[SuspectedAdverseEvent]] = {}
    for event in events:
        grouped.setdefault(event.patient_id, []).append(event)
    return grouped


def build_daily_summary_message(events: list[SuspectedAdverseEvent]) -> tuple[str, list[str]]:
    """Return (alert message, sorted unique symptom names) for one patient's events."""
    names = sorted({str(s.get("name")) for event in events for s in event.symptoms if s.get("name")})
    message = f"Tổng hợp {len(events)} ghi nhận triệu chứng trong ngày: {', '.join(names)}"
    return message, names


class AdverseEventSummaryService:
    """Creates one MEDIUM SUSPECTED_ADVERSE_EVENT alert per patient for the last
    24h of un-notified LOW/MODERATE events. Caller owns the transaction."""

    def __init__(
        self,
        event_repository: SuspectedAdverseEventRepository,
        alert_repository: AlertRepository,
    ) -> None:
        self._events = event_repository
        self._alerts = alert_repository

    async def summarize_daily(self, now: datetime) -> int:
        """Returns the number of summary alerts created."""
        rows = await self._events.list_pending_daily_summary(now - timedelta(hours=24))
        created = 0
        for patient_id, events in group_events_by_patient(rows).items():
            message, names = build_daily_summary_message(events)
            alert = await self._alerts.create_alert(
                patient_id=patient_id,
                triggered_by_type="ADVERSE_EVENT",
                alert_type="SUSPECTED_ADVERSE_EVENT",
                severity="MEDIUM",
                message=message,
                metadata={
                    "adverse_event_ids": [str(event.id) for event in events],
                    "symptoms": names,
                    "summary_type": "DAILY",
                },
            )
            await self._events.mark_summarized([event.id for event in events], now, alert.id)
            created += 1
        return created
