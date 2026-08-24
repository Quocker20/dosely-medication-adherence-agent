from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.common.exceptions import register_exception_handlers
from src.common.middleware import RequestContextMiddleware
from src.core.config import get_settings
from src.core.redis import close_redis_connection
from src.core.firebase_app import init_firebase
from src.api.v1_router import v1_router
from src.modules.dashboard.router import ws_router as dashboard_ws_router

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
DOWNLOADS_DIR = Path(__file__).resolve().parent.parent / "downloads"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"Starting {settings.app_name} in {settings.app_env} mode")
    init_firebase()
    yield
    await close_redis_connection()
    print("Shutting down...")


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="RemindRx Medication Adherence Core API",
    version="1.0.0",
    lifespan=lifespan,
)

# Register Middleware
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Exception Handlers
register_exception_handlers(app)

# Register API v1 Router
app.include_router(v1_router, prefix="/api/v1")

# WebSocket handlers sit at the app root, not under /api/v1 — api-contract.md
# registers the dashboard feed as /ws/dashboard. Registered before the static
# mount below so the catch-all does not shadow it.
app.include_router(dashboard_ws_router)


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}


# File APK để tải trực tiếp (xem docs/android-app-testing.md). Bind-mount riêng
# ngoài image Docker nên cập nhật APK không cần build lại image.
if DOWNLOADS_DIR.is_dir():
    app.mount("/downloads", StaticFiles(directory=DOWNLOADS_DIR), name="downloads")

# Portal bác sĩ đã build (npm run build trong web/) được serve ngay từ FastAPI.
# Lúc dev thì chạy `npm run dev` — Vite proxy /api sang cổng 8000.
# Mount sau cùng vì đây là catch-all "/" — mount trước nó sẽ bị che khuất.
if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="portal")
