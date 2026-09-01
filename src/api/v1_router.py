from fastapi import APIRouter

from src.modules.adherence.adverse_events_router import router as adverse_events_router
from src.modules.adherence.router import (
    alerts_router,
    dose_actions_router,
    health_surveys_router,
    patients_adherence_router,
)
from src.modules.adherence_review.router import (
    admin_adherence_reviews_router,
    adherence_reviews_router,
)
from src.modules.agents.router import agent_runs_router, chat_router, schedules_router
from src.modules.app_update.router import router as app_update_router
from src.modules.auth.router import router as auth_router
from src.modules.caregivers.router import router as caregivers_router
from src.modules.dashboard.router import router as dashboard_router
from src.modules.patients.router import router as patients_router
from src.modules.patients.router import self_router as patients_self_router
from src.modules.prescriptions.router import prescriptions_router as prescriptions_crud_router
from src.modules.prescriptions.router import router as prescriptions_router

v1_router = APIRouter()

v1_router.include_router(auth_router)
v1_router.include_router(app_update_router)
v1_router.include_router(caregivers_router)
v1_router.include_router(patients_router)
v1_router.include_router(patients_self_router)
v1_router.include_router(prescriptions_router)
v1_router.include_router(prescriptions_crud_router)
v1_router.include_router(schedules_router)
v1_router.include_router(agent_runs_router)
v1_router.include_router(dose_actions_router)
v1_router.include_router(patients_adherence_router)
v1_router.include_router(alerts_router)
v1_router.include_router(health_surveys_router)
v1_router.include_router(adverse_events_router)
v1_router.include_router(chat_router)
v1_router.include_router(dashboard_router)
v1_router.include_router(adherence_reviews_router)
v1_router.include_router(admin_adherence_reviews_router)
