import logging
import uuid
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.prescriptions.models import Medication

logger = logging.getLogger(__name__)


class MedicationRepository:
    """Repository handling Medication catalog database operations."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_medication_by_id(self, medication_id: uuid.UUID) -> Optional[Medication]:
        """Fetch a single medication by ID."""
        stmt = select(Medication).where(Medication.id == medication_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_medications(
        self,
        page: int = 1,
        size: int = 10,
        search: Optional[str] = None,
        active_only: bool = True,
    ) -> Tuple[List[Medication], int]:
        """Fetch paginated medication catalog entries.

        Count is a separate query rather than count().over() — the window
        function forces the planner to materialize the full filtered result
        before LIMIT can apply, which is a full scan on every page request.
        """
        filters = []
        if active_only:
            filters.append(Medication.is_active.is_(True))
        if search and search.strip():
            filters.append(Medication.name.ilike(f"%{search.strip()}%"))

        count_stmt = select(func.count(Medication.id))
        if filters:
            count_stmt = count_stmt.where(*filters)
        total_count = (await self._db.execute(count_stmt)).scalar_one()

        if total_count == 0:
            return [], 0

        base_stmt = select(Medication)
        if filters:
            base_stmt = base_stmt.where(*filters)

        offset = (page - 1) * size
        stmt = (
            base_stmt.order_by(Medication.name.asc(), Medication.id.asc())
            .offset(offset)
            .limit(size)
        )
        result = await self._db.execute(stmt)
        items = [row[0] for row in result.all()]
        return items, total_count
