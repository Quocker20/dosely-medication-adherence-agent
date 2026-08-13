from fastapi import APIRouter
from src.modules.admin.router import router as admin_router
from src.modules.adherence.router import (
    alerts_router,
    dose_actions_router,
    patients_adherence_router,
)
from src.modules.agents.router import agent_runs_router, schedules_router
from src.modules.auth.router import router as auth_router
from src.modules.patients.router import router as patients_router
from src.modules.patients.router import self_router as patients_self_router
from src.modules.prescriptions.router import router as prescriptions_router
from src.modules.prescriptions.router import prescriptions_router as prescriptions_crud_router

v1_router = APIRouter()

v1_router.include_router(auth_router)
v1_router.include_router(admin_router)
v1_router.include_router(patients_router)
v1_router.include_router(patients_self_router)
v1_router.include_router(prescriptions_router)
v1_router.include_router(prescriptions_crud_router)
v1_router.include_router(schedules_router)
v1_router.include_router(agent_runs_router)
v1_router.include_router(dose_actions_router)
v1_router.include_router(patients_adherence_router)
v1_router.include_router(alerts_router)
