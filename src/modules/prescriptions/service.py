import logging
import math
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.common.exceptions import NotFoundException
from src.common.schemas import PageResponse
from src.modules.prescriptions.repository import MedicationRepository
from src.modules.prescriptions.schemas import MedicationDetailResponse

logger = logging.getLogger(__name__)


class MedicationService:
    """Service handling Medication catalog read operations."""

    def __init__(self, db: AsyncSession, medication_repository: MedicationRepository) -> None:
        self._db = db
        self._medication_repo = medication_repository

    async def list_medications(
        self, page: int = 1, size: int = 10, search: Optional[str] = None
    ) -> PageResponse[MedicationDetailResponse]:
        """Fetch paginated medication catalog."""
        items, total_count = await self._medication_repo.list_medications(
            page=page, size=size, search=search, active_only=True
        )

        total_pages = math.ceil(total_count / size) if total_count > 0 else 0
        last = page >= total_pages if total_pages > 0 else True

        content = [MedicationDetailResponse.model_validate(m) for m in items]

        return PageResponse(
            content=content,
            page_no=page,
            page_size=size,
            total_elements=total_count,
            total_pages=total_pages,
            last=last,
        )

    async def get_medication(self, medication_id: uuid.UUID) -> MedicationDetailResponse:
        """Fetch single medication detail by ID."""
        medication = await self._medication_repo.get_medication_by_id(medication_id)
        if medication is None:
            raise NotFoundException(message="Medication not found")
        return MedicationDetailResponse.model_validate(medication)
