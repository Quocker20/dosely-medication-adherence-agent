from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.common.exceptions import register_exception_handlers
from src.common.middleware import RequestContextMiddleware
from src.core.config import get_settings
from src.core.redis import close_redis_connection
from src.api.v1_router import v1_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"Starting {settings.app_name} in {settings.app_env} mode")
    yield
    await close_redis_connection()
    print("Shutting down...")


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="ADHE REMIND Medication Adherence Core API",
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


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}
