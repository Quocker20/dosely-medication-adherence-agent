import asyncio
import logging
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, require_roles
from src.common.exceptions import UnauthorizedException
from src.core.response import success_response
from src.core.security import decode_token
from src.modules.dashboard.repository import DashboardRepository
from src.modules.dashboard.service import DashboardEventService, DashboardService

logger = logging.getLogger(__name__)

_WS_ALLOWED_ROLES = ("DOCTOR", "ADMIN")
_WS_POLICY_VIOLATION = 1008


def get_dashboard_service(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> DashboardService:
    """Dependency factory providing DashboardService instance."""
    return DashboardService(db=db, dashboard_repository=DashboardRepository(db))


DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]
DoctorOrAdminUserDep = Annotated[dict, Depends(require_roles("DOCTOR", "ADMIN"))]

router = APIRouter(prefix="/dashboard", tags=["Dashboard & Realtime"])
ws_router = APIRouter(tags=["Dashboard & Realtime"])


@router.get("/patients")
async def list_dashboard_patients(
    current_user: DoctorOrAdminUserDep,
    service: DashboardServiceDep,
    page: int = Query(1, ge=1, le=1000, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
    alert_status: Optional[str] = Query(
        None, alias="alertStatus", pattern=r"^(OPEN|ACKNOWLEDGED|RESOLVED)$"
    ),
    search: Optional[str] = Query(None, min_length=2, description="Search by name or phone"),
) -> JSONResponse:
    """Doctor portal roster (Doctor/Admin). A doctor sees only patients they
    have prescribed for; an admin sees all. Ordered by open alert count so the
    patients needing attention sit at the top of page 1."""
    result = await service.list_patients(
        actor_payload=current_user,
        page=page,
        size=size,
        alert_status=alert_status,
        search=search,
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Dashboard patient list fetched successfully",
    )


@router.get("/patients/{patient_id}")
async def get_dashboard_patient_detail(
    patient_id: uuid.UUID,
    current_user: DoctorOrAdminUserDep,
    service: DashboardServiceDep,
) -> JSONResponse:
    """Single-patient panel (Doctor/Admin): active prescriptions, rolling
    adherence, and recent alerts. Out-of-scope and non-existent both return
    404 so the endpoint cannot enumerate patient UUIDs."""
    result = await service.get_patient_detail(
        patient_id=patient_id, actor_payload=current_user
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Dashboard patient detail fetched successfully",
    )


def _authorize_ws_token(token: Optional[str]) -> dict:
    """Validate the handshake token for a dashboard socket.

    The token arrives as a query parameter because the browser WebSocket API
    cannot set an Authorization header. That is a real tradeoff — query strings
    leak into proxy and browser history logs far more readily than headers — so
    keep dashboard tokens short-lived, and note that RequestContextMiddleware
    logs only `url.path`, never the query string.
    """
    if not token:
        raise UnauthorizedException(message="Missing authentication token")
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise UnauthorizedException(message="Invalid token type")
    if payload.get("role") not in _WS_ALLOWED_ROLES:
        raise UnauthorizedException(message="Role is not authorized for the dashboard feed")
    return payload


@ws_router.websocket("/ws/dashboard")
async def dashboard_events_socket(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
) -> None:
    """Live dashboard feed (Doctor/Admin), one JSON WebSocketEventStream frame
    per event.

    Authorised before `accept()`: a rejected handshake must never look like a
    momentarily-connected socket. HTTP exception handlers do not apply to a
    WebSocket route, so the failure is turned into a 1008 close here rather
    than propagating as an AppException nothing would render.
    """
    try:
        _authorize_ws_token(token)
    except UnauthorizedException as exc:
        await websocket.close(code=_WS_POLICY_VIOLATION, reason=exc.message)
        return

    await websocket.accept()

    async def _pump() -> None:
        async for frame in DashboardEventService.stream():
            await websocket.send_json(frame)

    async def _watch_disconnect() -> None:
        # Nothing is expected from the client; this read exists purely so a
        # disconnect is noticed. Without it, a socket that drops during a quiet
        # period would hold its Redis subscription open until the next event.
        while True:
            await websocket.receive_text()

    pump = asyncio.create_task(_pump())
    watch = asyncio.create_task(_watch_disconnect())
    try:
        done, pending = await asyncio.wait(
            {pump, watch}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                raise exc
    except WebSocketDisconnect:
        pass
    finally:
        for task in (pump, watch):
            task.cancel()
