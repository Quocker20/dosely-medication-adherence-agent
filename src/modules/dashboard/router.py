import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, require_roles
from src.common.exceptions import ForbiddenException, UnauthorizedException
from src.core.response import success_response
from src.core.security import decode_token
from src.modules.dashboard.repository import DashboardRepository
from src.modules.dashboard.service import DashboardEventService, DashboardService

logger = logging.getLogger(__name__)

_WS_ALLOWED_ROLES = ("DOCTOR", "ADMIN")
_PATIENT_WS_ALLOWED_ROLES = ("PATIENT",)


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
    alert_status: str | None = Query(
        None, alias="alertStatus", pattern=r"^(OPEN|ACKNOWLEDGED|RESOLVED)$"
    ),
    adherence_band: str | None = Query(
        None, alias="adherenceBand", pattern=r"^(LOW|MEDIUM|HIGH)$"
    ),
    search: str | None = Query(None, min_length=2, description="Search by name or phone"),
) -> JSONResponse:
    """Doctor portal roster (Doctor/Admin). A doctor sees only patients they
    have prescribed for; an admin sees all. Ordered by open alert count so the
    patients needing attention sit at the top of page 1."""
    result = await service.list_patients(
        actor_payload=current_user,
        page=page,
        size=size,
        alert_status=alert_status,
        adherence_band=adherence_band,
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


# --- WebSocket protocol (SEC-07 / P-04) ------------------------------------
#
# The token is NOT accepted in the URL any more (query strings reach proxy and
# browser-history logs). Flow:
#   1. client connects to /ws/dashboard or /ws/patient (no query string)
#   2. server accepts, and waits up to WS_AUTH_TIMEOUT_SECONDS for the first
#      text frame: {"type": "auth", "token": "<access token>"}
#   3. valid -> server replies {"type": "auth_ok", "expires_in": <seconds>} and
#      starts streaming event frames; invalid/late -> close 4401 (bad/expired/
#      missing token, timeout) or 4403 (valid token, wrong role)
#   4. the socket is closed with 4401 when the access token expires. The client
#      may send {"type": "auth", "token": <new token of the SAME user>} at any
#      time to extend it without reconnecting; {"type": "ping"} gets
#      {"type": "pong"}.
WS_AUTH_TIMEOUT_SECONDS = 5.0
WS_CLOSE_UNAUTHENTICATED = 4401
WS_CLOSE_FORBIDDEN = 4403
WS_CLOSE_TOO_BIG = 1009
WS_MAX_CLIENT_FRAME_CHARS = 8192


def _authorize_ws_token(token: str | None, allowed_roles: tuple[str, ...]) -> dict:
    """Validate an access token presented in the auth frame.

    Raises UnauthorizedException for bad/expired tokens and ForbiddenException
    when the token is fine but the role may not use this feed.
    """
    if not token or not isinstance(token, str):
        raise UnauthorizedException(message="Missing authentication token")
    payload = decode_token(token)  # raises on bad signature / expired
    if payload.get("type") != "access":
        raise UnauthorizedException(message="Invalid token type")
    if payload.get("role") not in allowed_roles:
        raise ForbiddenException(message="Role is not authorized for this feed")
    try:
        uuid.UUID(str(payload["sub"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise UnauthorizedException(message="Invalid identity") from exc
    return payload


def _parse_auth_frame(text: str) -> str | None:
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if isinstance(data, dict) and data.get("type") == "auth":
        token = data.get("token")
        return token if isinstance(token, str) else None
    return None


async def _authenticate_ws(
    websocket: WebSocket, allowed_roles: tuple[str, ...]
) -> dict | None:
    """Accept the socket and authenticate it from the first frame.

    Returns the token payload, or None after closing the socket.
    """
    await websocket.accept()
    try:
        text = await asyncio.wait_for(
            websocket.receive_text(), timeout=WS_AUTH_TIMEOUT_SECONDS
        )
    except TimeoutError:
        await websocket.close(code=WS_CLOSE_UNAUTHENTICATED, reason="authentication timeout")
        return None
    except WebSocketDisconnect:
        return None
    if len(text) > WS_MAX_CLIENT_FRAME_CHARS:
        await websocket.close(code=WS_CLOSE_TOO_BIG, reason="frame too large")
        return None
    try:
        payload = _authorize_ws_token(_parse_auth_frame(text), allowed_roles)
    except ForbiddenException as exc:
        await websocket.close(code=WS_CLOSE_FORBIDDEN, reason=exc.message)
        return None
    except UnauthorizedException as exc:
        await websocket.close(code=WS_CLOSE_UNAUTHENTICATED, reason=exc.message)
        return None
    await _send_auth_ok(websocket, payload)
    return payload


async def _send_auth_ok(websocket: WebSocket, payload: dict) -> None:
    await websocket.send_json(
        {"type": "auth_ok", "expires_in": max(int(payload["exp"] - time.time()), 0)}
    )


async def _watch_client(
    websocket: WebSocket, payload: dict, allowed_roles: tuple[str, ...]
) -> None:
    """Read client frames and enforce token expiry.

    Returns (after closing the socket) when the token expires or the client
    sends something unacceptable; raises WebSocketDisconnect when the peer
    leaves. Re-authentication must be for the same subject so a socket can
    never be switched to a different user.
    """
    expires_at = float(payload["exp"])
    while True:
        remaining = expires_at - time.time()
        if remaining <= 0:
            await websocket.close(code=WS_CLOSE_UNAUTHENTICATED, reason="token expired")
            return
        try:
            text = await asyncio.wait_for(websocket.receive_text(), timeout=remaining)
        except TimeoutError:
            continue  # loop head closes the socket once expired
        if time.time() >= expires_at:
            await websocket.close(code=WS_CLOSE_UNAUTHENTICATED, reason="token expired")
            return
        if len(text) > WS_MAX_CLIENT_FRAME_CHARS:
            await websocket.close(code=WS_CLOSE_TOO_BIG, reason="frame too large")
            return
        try:
            message = json.loads(text)
        except ValueError:
            continue
        if not isinstance(message, dict):
            continue
        if message.get("type") == "ping":
            await websocket.send_json({"type": "pong"})
        elif message.get("type") == "auth":
            try:
                fresh = _authorize_ws_token(message.get("token"), allowed_roles)
            except ForbiddenException as exc:
                await websocket.close(code=WS_CLOSE_FORBIDDEN, reason=exc.message)
                return
            except UnauthorizedException as exc:
                await websocket.close(code=WS_CLOSE_UNAUTHENTICATED, reason=exc.message)
                return
            if fresh["sub"] != payload["sub"]:
                await websocket.close(
                    code=WS_CLOSE_FORBIDDEN, reason="token subject changed"
                )
                return
            expires_at = float(fresh["exp"])
            await _send_auth_ok(websocket, fresh)


async def _serve_ws(
    websocket: WebSocket,
    allowed_roles: tuple[str, ...],
    frames: Callable[[dict], AsyncIterator[dict]],
) -> None:
    """Authenticate, then pump `frames(payload)` to the client until the client
    leaves, the token expires, or the feed ends."""
    payload = await _authenticate_ws(websocket, allowed_roles)
    if payload is None:
        return

    async def _pump() -> None:
        async for frame in frames(payload):
            await websocket.send_json(frame)

    pump = asyncio.create_task(_pump())
    watch = asyncio.create_task(_watch_client(websocket, payload, allowed_roles))
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


@ws_router.websocket("/ws/dashboard")
async def dashboard_events_socket(websocket: WebSocket) -> None:
    """Live dashboard feed (Doctor/Admin), one JSON WebSocketEventStream frame
    per event. Authenticated by the first message (see protocol above).

    No `Depends(get_db)` on purpose (P-04): the doctor-scope check opens a
    short session per frame instead of pinning one connection for the socket's
    lifetime. HTTP exception handlers do not apply to WebSocket routes, so
    failures become close codes here.
    """
    await _serve_ws(
        websocket,
        _WS_ALLOWED_ROLES,
        lambda payload: DashboardEventService.stream_for_dashboard_actor(payload),
    )


@ws_router.websocket("/ws/patient")
async def patient_events_socket(websocket: WebSocket) -> None:
    """Live patient feed, filtered server-side to the token subject.

    Event payloads deliberately contain identifiers/status only.  Clients use
    their authenticated REST calls to reload authoritative routine and
    schedule data after an event arrives.
    """
    await _serve_ws(
        websocket,
        _PATIENT_WS_ALLOWED_ROLES,
        lambda payload: DashboardEventService.stream_patient(uuid.UUID(payload["sub"])),
    )
