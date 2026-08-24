import logging
import math
import uuid
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from typing import Any, AsyncIterator, Dict, Optional

from pydantic import ValidationError

from src.common.exceptions import NotFoundException
from src.common.schemas import PageResponse
from src.core.config import get_settings
from src.core.redis import subscribe_dashboard_events
from src.modules.adherence.schemas import AlertDetailResponse
from src.modules.dashboard.repository import DashboardRepository
from src.modules.dashboard.schemas import (
    DashboardAdherenceSummary,
    DashboardPatientDetailResponse,
    DashboardPatientListResponse,
    DashboardPatientSummary,
    WebSocketEventStream,
)

logger = logging.getLogger(__name__)


def _adherence_rate(taken: int, total: int) -> float:
    """Same formula as AdherenceLogService.get_adherence_summary — the two
    numbers are shown side by side in the portal and must not disagree."""
    return round((taken / total) * 100.0, 2) if total > 0 else 0.0


class DashboardService:
    """Read-only aggregation for the doctor portal (slice 8).

    Holds no transactions: every method reads. RBAC narrows to DOCTOR/ADMIN at
    the router; the per-patient scope (a doctor sees only patients they have
    prescribed for, an admin sees all) is applied here by passing doctor_id
    down to the repository, mirroring PatientService.list_patients.
    """

    def __init__(self, db, dashboard_repository: DashboardRepository) -> None:
        self._db = db
        self._repo = dashboard_repository

    @staticmethod
    def _scope_doctor_id(actor_payload: dict) -> Optional[uuid.UUID]:
        """None for ADMIN (unscoped), the doctor's own id otherwise."""
        if actor_payload.get("role") == "ADMIN":
            return None
        return uuid.UUID(actor_payload["sub"])

    @staticmethod
    def _window_start() -> datetime:
        settings = get_settings()
        return datetime.now(dt_timezone.utc) - timedelta(
            days=settings.dashboard_adherence_window_days
        )

    async def list_patients(
        self,
        actor_payload: dict,
        page: int = 1,
        size: int = 10,
        alert_status: Optional[str] = None,
        adherence_band: Optional[str] = None,
        search: Optional[str] = None,
    ) -> PageResponse[DashboardPatientListResponse]:
        """Roster page, most-alerting patients first. A doctor with no
        prescriptions gets an empty page rather than a 403 — same list-style
        filtering as PatientService.list_patients, which avoids leaking whether
        any patients exist at all."""
        rows, total_count = await self._repo.list_dashboard_patients(
            range_start=self._window_start(),
            doctor_id=self._scope_doctor_id(actor_payload),
            page=page,
            size=size,
            alert_status=alert_status,
            adherence_band=adherence_band,
            search=search,
        )

        total_pages = math.ceil(total_count / size) if total_count > 0 else 0
        last = page >= total_pages if total_pages > 0 else True

        content = [
            DashboardPatientListResponse(
                patient_id=patient_id,
                patient_name=name,
                adherence_rate=_adherence_rate(taken, total),
                open_alerts_count=open_alerts,
                last_survey_date=last_survey,
            )
            for patient_id, name, total, taken, open_alerts, last_survey in rows
        ]

        return PageResponse(
            content=content,
            page_no=page,
            page_size=size,
            total_elements=total_count,
            total_pages=total_pages,
            last=last,
        )

    async def get_patient_detail(
        self, patient_id: uuid.UUID, actor_payload: dict
    ) -> DashboardPatientDetailResponse:
        """Single-patient panel. Out of scope and non-existent both raise 404,
        so the endpoint cannot be used to enumerate patient UUIDs."""
        settings = get_settings()
        identity = await self._repo.get_patient_identity(
            patient_id, doctor_id=self._scope_doctor_id(actor_payload)
        )
        if identity is None:
            raise NotFoundException(message="Patient not found")

        user_id, name, phone = identity
        range_start = self._window_start()

        active_count = await self._repo.count_active_prescriptions(patient_id)
        total, taken, skipped, missed = await self._repo.get_dose_status_counts(
            patient_id, range_start
        )
        alerts = await self._repo.list_recent_alerts(
            patient_id, limit=settings.dashboard_recent_alerts_limit
        )

        return DashboardPatientDetailResponse(
            patient=DashboardPatientSummary(user_id=user_id, name=name, phone=phone),
            active_prescriptions_count=active_count,
            adherence_summary=DashboardAdherenceSummary(
                adherence_rate=_adherence_rate(taken, total),
                total_doses=total,
                taken_doses=taken,
                skipped_doses=skipped,
                missed_doses=missed,
                window_days=settings.dashboard_adherence_window_days,
            ),
            recent_alerts=[AlertDetailResponse.model_validate(a) for a in alerts],
        )


class DashboardEventService:
    """Consumer side of the live dashboard feed.

    Consume-only by design. Publishing lives in core/redis.py because the
    publishers are other slices' write paths (an alert being raised, a dose
    being logged) — routing those through this module would make every slice
    that emits an event depend on the dashboard, which is exactly the coupling
    structure.md's vertical-slice isolation exists to prevent.
    """

    @staticmethod
    async def stream() -> AsyncIterator[Dict[str, Any]]:
        """Frames for one connected client, in arrival order.

        Each frame is validated against WebSocketEventStream on the way out, so
        a publisher that drifts from the documented shape is dropped here
        rather than reaching the portal as something it cannot parse.
        """
        async for raw in subscribe_dashboard_events():
            try:
                frame = WebSocketEventStream.model_validate(raw)
            except ValidationError:
                logger.warning("Dropping dashboard frame that failed schema validation")
                continue
            yield frame.model_dump(mode="json")
