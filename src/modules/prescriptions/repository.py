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
        """Fetch paginated medication catalog entries in a single query."""
        total_count_col = func.count().over().label("total_count")
        base_stmt = select(Medication, total_count_col)

        filters = []
        if active_only:
            filters.append(Medication.is_active.is_(True))
        if search and search.strip():
            filters.append(Medication.name.ilike(f"%{search.strip()}%"))

        if filters:
            base_stmt = base_stmt.where(*filters)

        offset = (page - 1) * size
        stmt = (
            base_stmt.order_by(Medication.name.asc(), Medication.id.asc())
            .offset(offset)
            .limit(size)
        )
        result = await self._db.execute(stmt)
        rows = result.all()

        if not rows:
            if page == 1:
                return [], 0
            count_stmt = select(func.count(Medication.id))
            if filters:
                count_stmt = count_stmt.where(*filters)
            total_count = (await self._db.execute(count_stmt)).scalar_one()
            return [], total_count

        total_count = rows[0].total_count if rows else 0
        items = [row[0] for row in rows]
        return items, total_count
