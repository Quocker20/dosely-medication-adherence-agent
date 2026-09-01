import logging
import uuid
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import Exists, delete, func, or_, select, update
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.patients.models import CaregiverLink
from src.modules.prescriptions.models import Medication, Prescription, PrescriptionItem

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

    async def list_by_ids(
        self, medication_ids: List[uuid.UUID]
    ) -> Dict[uuid.UUID, Medication]:
        """Batch-resolve medications by ID (IN clause) instead of one query
        per ID — avoids N+1 when rendering a prescription's item list (e.g.
        the PDF export). Rides the medications PK. medication_id carries no
        FK, so callers may pass IDs for rows since deleted; those are simply
        absent from the returned mapping."""
        if not medication_ids:
            return {}
        stmt = select(Medication).where(Medication.id.in_(medication_ids))
        result = await self._db.execute(stmt)
        return {m.id: m for m in result.scalars().all()}

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


class PrescriptionRepository:
    """Repository handling Prescription and PrescriptionItem database operations."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @staticmethod
    def _has_prescribed_filter(
        doctor_id: uuid.UUID, patient_id_col: ColumnElement
    ) -> Exists:
        """Build the access predicate for a doctor reaching patient data.

        Mirrors PatientRepository._has_prescribed_filter (duplicated rather
        than imported to keep this module self-contained per structure.md's
        vertical-slice rule). patient_id_col is supplied by the caller rather
        than hardcoded — an EXISTS only auto-correlates to a table already
        present in the enclosing query's FROM, so hardcoding it would silently
        produce an uncorrelated subquery from a query that never joins
        Prescription/PatientProfile.
        """
        return (
            select(Prescription.id)
            .where(
                Prescription.doctor_id == doctor_id,
                Prescription.patient_id == patient_id_col,
            )
            .exists()
        )

    @staticmethod
    def _has_active_caregiver_filter(
        caregiver_user_id: uuid.UUID, patient_id_col: ColumnElement
    ) -> Exists:
        """Build the access predicate for a caregiver reaching a patient's
        prescriptions. Mirrors PatientRepository._has_active_caregiver_filter,
        parameterized on patient_id_col for the same correlation-safety reason.
        """
        return (
            select(CaregiverLink.id)
            .where(
                CaregiverLink.caregiver_user_id == caregiver_user_id,
                CaregiverLink.patient_id == patient_id_col,
                CaregiverLink.status == "ACTIVE",
            )
            .exists()
        )

    @staticmethod
    def _access_filter(actor_id: uuid.UUID, patient_id_col: ColumnElement):
        """Role-agnostic access predicate: self-owned, doctor-prescribed, or
        active-caregiver-linked are independent facts, checked together so one
        account can qualify through more than one (mirrors
        PatientRepository.get_routine's access derivation)."""
        return or_(
            patient_id_col == actor_id,
            PrescriptionRepository._has_prescribed_filter(actor_id, patient_id_col),
            PrescriptionRepository._has_active_caregiver_filter(actor_id, patient_id_col),
        )

    # ── Prescription (header) ──

    async def create_prescription(
        self,
        patient_id: uuid.UUID,
        doctor_id: uuid.UUID,
        diagnosis_note: Optional[str] = None,
    ) -> Prescription:
        """Persist a new DRAFT prescription header."""
        prescription = Prescription(
            patient_id=patient_id, doctor_id=doctor_id, diagnosis_note=diagnosis_note
        )
        self._db.add(prescription)
        await self._db.flush()
        return prescription

    async def get_by_id(
        self, prescription_id: uuid.UUID, actor_id: Optional[uuid.UUID] = None
    ) -> Optional[Prescription]:
        """Fetch a prescription by ID. actor_id=None means unscoped (ADMIN);
        otherwise restricted to self/doctor-prescribed/active-caregiver."""
        stmt = select(Prescription).where(Prescription.id == prescription_id)
        if actor_id is not None:
            stmt = stmt.where(self._access_filter(actor_id, Prescription.patient_id))
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_for_doctor(
        self, prescription_id: uuid.UUID, doctor_id: uuid.UUID
    ) -> Optional[Prescription]:
        """Fetch a prescription scoped to the doctor who created it (ownership
        check), used to disambiguate 404 (not found/not owner) vs 422 (wrong
        status) after a failed conditional state-transition UPDATE."""
        stmt = select(Prescription).where(
            Prescription.id == prescription_id, Prescription.doctor_id == doctor_id
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def lock_for_items(
        self, prescription_id: uuid.UUID, doctor_id: uuid.UUID
    ) -> Optional[Prescription]:
        """SELECT ... FOR UPDATE the prescription row, scoped to owning
        doctor. Held for the rest of the caller's transaction so a concurrent
        approve/cancel (which also takes a row lock via its UPDATE) cannot
        race an item add/edit/delete — whichever transaction commits first
        determines what the other sees."""
        stmt = (
            select(Prescription)
            .where(Prescription.id == prescription_id, Prescription.doctor_id == doctor_id)
            .with_for_update()
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_patient(
        self,
        patient_id: uuid.UUID,
        actor_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        page: int = 1,
        size: int = 10,
    ) -> Tuple[List[Prescription], int]:
        """Fetch paginated prescriptions for a patient, newest first.

        actor_id=None means unscoped (ADMIN). Otherwise restricted the same
        way as get_by_id — an actor with zero access sees an empty page
        rather than a 404 (list-style filtering, matching
        PatientRepository.list_patients).

        Count is a separate query rather than count().over() — the window
        function forces the planner to materialize the full filtered result
        before LIMIT can apply, which is a full scan on every page request.
        Rides idx_prescriptions_patient_created (patient_id, created_at DESC).
        """
        filters = [Prescription.patient_id == patient_id]
        if actor_id is not None:
            filters.append(self._access_filter(actor_id, Prescription.patient_id))
        if status:
            filters.append(Prescription.status == status)

        count_stmt = select(func.count(Prescription.id)).where(*filters)
        total_count = (await self._db.execute(count_stmt)).scalar_one()

        if total_count == 0:
            return [], 0

        offset = (page - 1) * size
        stmt = (
            select(Prescription)
            .where(*filters)
            .order_by(Prescription.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        result = await self._db.execute(stmt)
        items = [row[0] for row in result.all()]
        return items, total_count

    async def list_current_medications(
        self, patient_id: uuid.UUID, as_of: date
    ) -> List[PrescriptionItem]:
        """Return date-active items from APPROVED prescriptions for one patient."""
        stmt = (
            select(PrescriptionItem)
            .join(Prescription, Prescription.id == PrescriptionItem.prescription_id)
            .where(
                Prescription.patient_id == patient_id,
                Prescription.status == "APPROVED",
                PrescriptionItem.start_date <= as_of,
                or_(PrescriptionItem.end_date.is_(None), PrescriptionItem.end_date >= as_of),
            )
            .order_by(PrescriptionItem.display_name.asc(), PrescriptionItem.created_at.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def update_diagnosis_if_draft(
        self, prescription_id: uuid.UUID, doctor_id: uuid.UUID, diagnosis_note: Optional[str]
    ) -> Optional[Prescription]:
        """Atomic compare-and-swap: only updates a row still in DRAFT owned by
        this doctor. Returns None on no match (caller disambiguates 404 vs 422
        via get_by_id_for_doctor)."""
        stmt = (
            update(Prescription)
            .where(
                Prescription.id == prescription_id,
                Prescription.doctor_id == doctor_id,
                Prescription.status == "DRAFT",
            )
            .values(diagnosis_note=diagnosis_note)
            .returning(Prescription)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def approve_if_draft(
        self, prescription_id: uuid.UUID, doctor_id: uuid.UUID
    ) -> Optional[Prescription]:
        """Atomic DRAFT -> APPROVED compare-and-swap, sets approved_at."""
        stmt = (
            update(Prescription)
            .where(
                Prescription.id == prescription_id,
                Prescription.doctor_id == doctor_id,
                Prescription.status == "DRAFT",
            )
            .values(status="APPROVED", approved_at=func.now())
            .returning(Prescription)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def cancel_if_active(
        self, prescription_id: uuid.UUID, doctor_id: uuid.UUID
    ) -> Optional[Prescription]:
        """Atomic DRAFT/APPROVED -> CANCELLED compare-and-swap."""
        stmt = (
            update(Prescription)
            .where(
                Prescription.id == prescription_id,
                Prescription.doctor_id == doctor_id,
                Prescription.status.in_(("DRAFT", "APPROVED")),
            )
            .values(status="CANCELLED")
            .returning(Prescription)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    # ── PrescriptionItem ──

    async def bulk_create_items(
        self, prescription_id: uuid.UUID, items: List[Dict[str, Any]]
    ) -> List[PrescriptionItem]:
        """Insert multiple line items in one flush (single round trip, not a
        per-item loop) — used by atomic prescription creation."""
        if not items:
            return []
        rows = [PrescriptionItem(prescription_id=prescription_id, **fields) for fields in items]
        self._db.add_all(rows)
        await self._db.flush()
        return rows

    async def add_item(
        self, prescription_id: uuid.UUID, fields: Dict[str, Any]
    ) -> PrescriptionItem:
        """Insert a single line item onto an existing prescription."""
        item = PrescriptionItem(prescription_id=prescription_id, **fields)
        self._db.add(item)
        await self._db.flush()
        return item

    async def get_item(
        self, item_id: uuid.UUID, prescription_id: uuid.UUID
    ) -> Optional[PrescriptionItem]:
        """Fetch a single item scoped to its owning prescription — blocks an
        IDOR where a valid item_id from a different prescription is passed."""
        stmt = select(PrescriptionItem).where(
            PrescriptionItem.id == item_id, PrescriptionItem.prescription_id == prescription_id
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_items(self, prescription_id: uuid.UUID) -> List[PrescriptionItem]:
        """Fetch all items for one prescription. Rides
        idx_prescription_items_prescription_id."""
        stmt = (
            select(PrescriptionItem)
            .where(PrescriptionItem.prescription_id == prescription_id)
            .order_by(PrescriptionItem.created_at.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_items_for_prescriptions(
        self, prescription_ids: List[uuid.UUID]
    ) -> Dict[uuid.UUID, List[PrescriptionItem]]:
        """Batch-fetch items for many prescriptions in one query (IN clause)
        instead of one query per prescription — avoids N+1 on the list
        endpoint. Rides idx_prescription_items_prescription_id."""
        if not prescription_ids:
            return {}
        stmt = (
            select(PrescriptionItem)
            .where(PrescriptionItem.prescription_id.in_(prescription_ids))
            .order_by(PrescriptionItem.prescription_id, PrescriptionItem.created_at.asc())
        )
        result = await self._db.execute(stmt)
        mapping: Dict[uuid.UUID, List[PrescriptionItem]] = {}
        for item in result.scalars().all():
            mapping.setdefault(item.prescription_id, []).append(item)
        return mapping

    async def update_item(
        self, item_id: uuid.UUID, fields: Dict[str, Any]
    ) -> PrescriptionItem:
        """Update a line item by ID. Caller must already hold the DRAFT lock
        via lock_for_items before calling this."""
        stmt = (
            update(PrescriptionItem)
            .where(PrescriptionItem.id == item_id)
            .values(**fields)
            .returning(PrescriptionItem)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def delete_item(self, item_id: uuid.UUID) -> None:
        """Hard-delete a line item by ID. Caller must already hold the DRAFT
        lock via lock_for_items before calling this."""
        stmt = delete(PrescriptionItem).where(PrescriptionItem.id == item_id)
        await self._db.execute(stmt)
