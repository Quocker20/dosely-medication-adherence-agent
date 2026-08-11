from fastapi import APIRouter
from src.modules.admin.router import router as admin_router
from src.modules.auth.router import router as auth_router

v1_router = APIRouter()

v1_router.include_router(auth_router)
v1_router.include_router(admin_router)
