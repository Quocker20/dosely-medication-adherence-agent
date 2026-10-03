import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.caregivers.models import CaregiverLink

logger = logging.getLogger(__name__)


class CaregiverRepository:
    """Statement-only. Never commit()/rollback() -- the service layer owns
    the transaction (structure.md)."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_link(
        self,
        patient_id: uuid.UUID,
        phone: str,
        relationship: Optional[str],
        link_code: str,
    ) -> CaregiverLink:
        """Persist a new PENDING_BINDING link. Relies on
        uq_caregiver_links_patient_phone to reject a duplicate atomically
        via IntegrityError -- no pre-check SELECT (avoids TOCTOU)."""
        link = CaregiverLink(
            patient_id=patient_id,
            phone=phone,
            relationship_label=relationship,
            link_code=link_code,
        )
        self._db.add(link)
        await self._db.flush()
        return link

    async def list_by_patient(self, patient_id: uuid.UUID) -> List[CaregiverLink]:
        """One SELECT, no join. Every field the response DTO needs lives on
        this row already (see the model docstring) -- never selectinload
        notification_deliveries here."""
        stmt = select(CaregiverLink).where(CaregiverLink.patient_id == patient_id)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_link(
        self, link_id: uuid.UUID, patient_id: uuid.UUID
    ) -> Optional[CaregiverLink]:
        """Scoped to the owning patient -- blocks an IDOR where a valid
        link_id from a different patient is passed in the path."""
        stmt = select(CaregiverLink).where(
            CaregiverLink.id == link_id, CaregiverLink.patient_id == patient_id
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_link_by_id(self, link_id: uuid.UUID) -> Optional[CaregiverLink]:
        """Unscoped lookup by id alone -- used by the send task, which
        reaches a link only via a NotificationDelivery row's
        caregiver_link_id and has no patient_id to scope by at that point.
        Never exposed through the API (the router always uses the
        patient-scoped get_link)."""
        stmt = select(CaregiverLink).where(CaregiverLink.id == link_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_link(self, link_id: uuid.UUID) -> None:
        stmt = delete(CaregiverLink).where(CaregiverLink.id == link_id)
        await self._db.execute(stmt)

    async def bind_by_code(
        self, link_code: str, telegram_chat_id: int, now: datetime
    ) -> Optional[CaregiverLink]:
        """Atomic binding CAS. `WHERE link_code = :code AND telegram_chat_id
        IS NULL` is the claim -- two webhook updates racing on the same
        code can both attempt this; only the first sees telegram_chat_id IS
        NULL and rowcount > 0, the second's UPDATE matches zero rows
        (Postgres re-evaluates the predicate against the row the first
        writer just committed). Returns None on a lost race or an unknown
        code; caller treats None as "already bound elsewhere or invalid"
        without distinguishing which -- a bind confirmation should not leak
        which codes are real."""
        stmt = (
            update(CaregiverLink)
            .where(
                CaregiverLink.link_code == link_code,
                CaregiverLink.telegram_chat_id.is_(None),
            )
            .values(
                telegram_chat_id=telegram_chat_id,
                telegram_bound_at=now,
                telegram_last_interaction_at=now,
                status="ACTIVE",
                link_code=None,
            )
            .returning(CaregiverLink)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def touch_interaction(self, telegram_chat_id: int, occurred_at: datetime) -> None:
        """Refresh the interaction timestamp for every link this chat_id
        holds (one caregiver may be linked to several patients, all
        sharing one Telegram account). GREATEST guards against an
        out-of-order webhook delivery dragging the timestamp backward --
        Telegram does not guarantee update ordering and retries on
        non-2xx. A BLOCKED link is restored to ACTIVE here: any inbound
        update from that chat_id means the user unblocked the bot."""
        stmt = (
            update(CaregiverLink)
            .where(CaregiverLink.telegram_chat_id == telegram_chat_id)
            .values(
                telegram_last_interaction_at=func.greatest(
                    func.coalesce(CaregiverLink.telegram_last_interaction_at, occurred_at),
                    occurred_at,
                ),
                status="ACTIVE",
            )
        )
        await self._db.execute(stmt)

    async def mark_blocked(self, telegram_chat_id: int) -> None:
        """Called by the send task on a 403 (bot blocked/kicked) -- the
        system's own view of reachability self-heals without waiting for
        any external signal. Every link this chat_id holds is marked, same
        reasoning as touch_interaction: one Telegram account, possibly
        several links."""
        stmt = (
            update(CaregiverLink)
            .where(CaregiverLink.telegram_chat_id == telegram_chat_id)
            .values(status="BLOCKED")
        )
        await self._db.execute(stmt)

    async def set_inactive(self, telegram_chat_id: int) -> None:
        """Called on an inbound /stop -- the caregiver's own opt-out."""
        stmt = (
            update(CaregiverLink)
            .where(CaregiverLink.telegram_chat_id == telegram_chat_id)
            .values(status="INACTIVE")
        )
        await self._db.execute(stmt)

    async def update_last_message_sent(self, link_id: uuid.UUID, now: datetime) -> None:
        """Update last_message_sent_at for a given link."""
        stmt = (
            update(CaregiverLink)
            .where(CaregiverLink.id == link_id)
            .values(last_message_sent_at=now)
        )
        await self._db.execute(stmt)

    async def list_deliverable_for_patient(self, patient_id: uuid.UUID) -> List[CaregiverLink]:
        """Bound, ACTIVE links for one patient -- used by the alert-triggered
        send path (one alert, at most a handful of links; no batching
        needed here). No window check: Telegram has none."""
        return await self.list_deliverable_for_patients([patient_id])

    async def list_deliverable_for_patients(
        self, patient_ids: List[uuid.UUID]
    ) -> List[CaregiverLink]:
        """Same predicate as list_deliverable_for_patient, batched over an
        IN-list. Used by the nightly adherence-review loop, which can
        raise several RED_ALERTs in one run -- one query here plus one
        query for patient names is the whole cost, regardless of how many
        alerts fired that night."""
        if not patient_ids:
            return []
        stmt = select(CaregiverLink).where(
            CaregiverLink.patient_id.in_(patient_ids),
            CaregiverLink.telegram_chat_id.is_not(None),
            CaregiverLink.status == "ACTIVE",
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def claim_due_reports(
        self, now: datetime, report_interval_days: int
    ) -> List[CaregiverLink]:
        """Claim links due for the weekly CG_REPORT: bound, ACTIVE, and >=
        report_interval_days since the last report (or never sent). No
        window-open condition -- Telegram has none, unlike the Zalo
        predecessor this narrowed from (composite index there, single
        column here).

        The claim IS the WHERE clause of this single UPDATE -- no SELECT
        FOR UPDATE, no SKIP LOCKED (not a pattern used anywhere in this
        codebase; see AgentRunRepository.claim_run and
        AdherenceLogRepository.apply_dose_action_cas for the established
        idiom). A second concurrent caller running the identical statement
        blocks on the row locks the first holds; once the first commits,
        Postgres re-evaluates the predicate against the new row version
        (EvalPlanQual) -- last_report_sent_at is now current and the row no
        longer matches, so the second caller claims zero rows. Rides
        ix_caregiver_links_report_due.
        """
        report_cutoff = now - timedelta(days=report_interval_days)
        stmt = (
            update(CaregiverLink)
            .where(
                CaregiverLink.telegram_chat_id.is_not(None),
                CaregiverLink.status == "ACTIVE",
                (CaregiverLink.last_report_sent_at.is_(None))
                | (CaregiverLink.last_report_sent_at < report_cutoff),
            )
            .values(last_report_sent_at=now, last_message_sent_at=now)
            .returning(CaregiverLink)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
