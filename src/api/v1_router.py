from fastapi import APIRouter

v1_router = APIRouter()

# Module sub-routers will be included here as modules are developed:
# from src.modules.auth.router import router as auth_router
# v1_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
