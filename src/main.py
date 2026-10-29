import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.v1_router import v1_router
from src.chatbot.clients.backend_client import close_client as close_backend_client
from src.common.body_limit import VoiceBodyLimitMiddleware
from src.common.exceptions import register_exception_handlers
from src.common.middleware import RequestContextMiddleware
from src.core.config import Settings, get_settings
from src.core.firebase_app import init_firebase
from src.core.logging_config import configure_logging
from src.core.redis import close_redis_connection
from src.modules.app_update.service import DOWNLOADS_DIR
from src.modules.caregivers.webhook_router import webhook_router
from src.modules.dashboard.router import ws_router as dashboard_ws_router
from src.rag_retrieval.provider import warm_up_rag

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Starting %s in %s mode", settings.app_name, settings.app_env)
    init_firebase()
    # P-09: warm the shared RAG index off the event loop; fail-soft.
    await asyncio.to_thread(warm_up_rag)
    yield
    await close_backend_client()
    await close_redis_connection()
    logger.info("Shutting down...")


CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
CORS_ALLOW_HEADERS = [
    "Authorization",
    "Content-Type",
    "Accept",
    "Accept-Language",
    "Idempotency-Key",
    "X-Request-ID",
]


def create_app(settings: Settings) -> FastAPI:
    """Build the FastAPI app for ``settings`` (a factory so tests can vary the env)."""
    configure_logging(settings.log_level)
    production = settings.app_env == "production"
    app = FastAPI(
        title=settings.app_name,
        description="Dosely Medication Adherence Core API",
        version="1.0.0",
        lifespan=lifespan,
        # SEC-14: no public API schema/Swagger in production.
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )

    # Register Middleware
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(VoiceBodyLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=CORS_ALLOW_METHODS,
        allow_headers=CORS_ALLOW_HEADERS,
    )

    # Register Exception Handlers
    register_exception_handlers(app)

    # Register API v1 Router
    app.include_router(v1_router, prefix="/api/v1")

    # WebSocket handlers sit at the app root, not under /api/v1 — api-contract.md
    # registers the dashboard feed as /ws/dashboard. Registered before the static
    # mount below so the catch-all does not shadow it.
    app.include_router(dashboard_ws_router)
    app.include_router(webhook_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    # File APK để tải trực tiếp (xem docs/android-app-testing.md). Bind-mount riêng
    # ngoài image Docker nên cập nhật APK không cần build lại image.
    if DOWNLOADS_DIR.is_dir():
        app.mount("/downloads", StaticFiles(directory=DOWNLOADS_DIR), name="downloads")

    # Portal bác sĩ đã build (npm run build trong web/) được serve ngay từ FastAPI.
    # Lúc dev thì chạy `npm run dev` — Vite proxy /api sang cổng 8000.
    # Mount sau cùng vì đây là catch-all "/" — mount trước nó sẽ bị che khuất.
    if WEB_DIST.is_dir():
        index_path = WEB_DIST / "index.html"

        async def serve_portal_spa() -> FileResponse:
            """Return the portal shell for client-side portal routes on refresh."""
            return FileResponse(index_path)

        # StaticFiles(html=True) only resolves index.html at the root or inside an
        # existing directory. These explicit routes preserve deep links such as
        # /doctor/patients, leaving API, WebSocket, and download routes untouched.
        for portal_prefix in ("admin", "doctor", "patient", "login"):
            app.add_api_route(f"/{portal_prefix}", serve_portal_spa, methods=["GET"], include_in_schema=False)
            app.add_api_route(
                f"/{portal_prefix}/{{rest:path}}",
                serve_portal_spa,
                methods=["GET"],
                include_in_schema=False,
            )

        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="portal")
    return app


app = create_app(get_settings())
