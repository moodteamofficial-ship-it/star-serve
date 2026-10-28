"""Tenant-scoped claim repositories with assignment visibility."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, false, func, literal, or_, select, text, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.database.repository import TenantAwareRepository
from app.core.exceptions import ResourceNotFoundError
from app.core.security.context import SecurityContext
from app.modules.claims.authorization import PERM_ASSIGN, PERM_VET, can_supervise
from app.modules.claims.models import (
    ApprovalPolicy,
    Claim,
    ClaimAmendment,
    ClaimApproval,
    ClaimAssignment,
    ClaimDocument,
    ClaimEvent,
    ClaimExternalReview,
    ClaimFollowup,
    ClaimNote,
    ClaimPayment,
    ClaimVetting,
    SegregationPolicy,
)
from app.modules.customers.models import Customer
from app.modules.tenants.models import Tenant
from app.modules.users.models import User


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, list):
        return value
    return []


class ClaimRepository(TenantAwareRepository[Claim]):
    model = Claim

    def _base_select(self) -> Select:
        stmt = select(self.model)
        if not self.ctx.is_platform_admin:
            stmt = stmt.where(Claim.tenant_id == self.ctx.tenant_id)
        return self._apply_branch_scope(stmt)

    def _visibility_filter(self, stmt: Select) -> Select:
        if can_supervise(self.ctx) or self.ctx.is_platform_admin:
            return stmt
        owned = or_(
            Claim.assigned_to_user_id == self.ctx.user_id,
            Claim.created_by_user_id == self.ctx.user_id,
        )
        if self.ctx.is_sales_agent:
            from app.modules.intermediaries.scope import agent_policy_ids

            return stmt.where(or_(owned, Claim.policy_id.in_(agent_policy_ids(self.ctx))))
        if self.ctx.allows(PERM_VET) or self.ctx.allows(PERM_ASSIGN):
            intake = and_(
                Claim.channel == "GUEST",
                Claim.assigned_to_user_id.is_(None),
                Claim.status.in_(
                    ("CLAIM_SUBMITTED", "ADDITIONAL_INFORMATION_REQUIRED", "VETTING")
                ),
            )
            return stmt.where(or_(owned, intake))
        return stmt.where(owned)

    def _visibility_select(self) -> Select:
        return self._visibility_filter(self._base_select())

    async def get(self, claim_id: UUID) -> Claim:
        stmt = self._visibility_select().where(Claim.id == claim_id)
        row = await self.session.scalar(stmt)
        if row is None:
            raise ResourceNotFoundError()
        return row

    async def get_for_update(self, claim_id: UUID) -> Claim:
        stmt = self._visibility_select().where(Claim.id == claim_id).with_for_update()
        row = await self.session.scalar(stmt)
        if row is None:
            raise ResourceNotFoundError()
        return row

    def _scope(self, stmt: Select) -> Select:
        if not self.ctx.is_platform_admin:
            stmt = stmt.where(Claim.tenant_id == self.ctx.tenant_id)
        return self._visibility_filter(self._apply_branch_scope(stmt))

    def _scoped_count(self) -> Select:
        return self._scope(select(func.count()).select_from(Claim))

    async def search(
        self,
        *,
        query: str | None,
        status: str | None,
        assigned_to_me: bool,
        queue: str | None,
        offset: int,
        limit: int,
        include_total: bool = True,
    ) -> tuple[list[Claim], int]:
        stmt = self._visibility_select()
        count_stmt = self._scoped_count()
        if status:
            stmt = stmt.where(Claim.status == status)
            count_stmt = count_stmt.where(Claim.status == status)
        if assigned_to_me:
            stmt = stmt.where(Claim.assigned_to_user_id == self.ctx.user_id)
            count_stmt = count_stmt.where(Claim.assigned_to_user_id == self.ctx.user_id)
        if queue:
            stmt = self._apply_queue(stmt, queue)
            count_stmt = self._apply_queue(count_stmt, queue)
        if query:
            like = f"%{query.strip()}%"
            filt = or_(
                Claim.claim_number.ilike(like),
                Claim.vehicle_registration.ilike(like),
                Claim.police_abstract_number.ilike(like),
            )
            stmt = stmt.where(filt)
            count_stmt = count_stmt.where(filt)
        total = int(await self.session.scalar(count_stmt) or 0) if include_total else 0
        stmt = stmt.order_by(Claim.updated_at.desc()).offset(offset).limit(limit)
        return list((await self.session.scalars(stmt)).all()), total

    async def search_listed(
        self,
        *,
        query: str | None,
        status: str | None,
        assigned_to_me: bool,
        queue: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[tuple[Claim, str | None, str | None, str | None]], int]:
        """One statement: visible page + names + window total."""
        assignee = aliased(User)
        stmt = (
            select(
                Claim,
                Customer.first_name,
                Customer.other_names,
                Customer.last_name,
                Tenant.trading_name,
                Tenant.legal_name,
                assignee.full_name,
                func.count().over().label("row_total"),
            )
            .select_from(Claim)
            .outerjoin(Customer, Customer.id == Claim.customer_id)
            .outerjoin(Tenant, Tenant.id == Claim.tenant_id)
            .outerjoin(assignee, assignee.id == Claim.assigned_to_user_id)
        )
        stmt = self._scope(stmt)
        if status:
            stmt = stmt.where(Claim.status == status)
        if assigned_to_me:
            stmt = stmt.where(Claim.assigned_to_user_id == self.ctx.user_id)
        if queue:
            stmt = self._apply_queue(stmt, queue)
        if query:
            like = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    Claim.claim_number.ilike(like),
                    Claim.vehicle_registration.ilike(like),
                    Claim.police_abstract_number.ilike(like),
                )
            )
        stmt = stmt.order_by(Claim.updated_at.desc()).offset(offset).limit(limit)
        rows = (await self.session.execute(stmt)).all()
        if rows:
            total = int(rows[0].row_total or 0)
        elif offset == 0:
            total = 0
        else:
            total = int(await self.session.scalar(self._scoped_count()) or 0)
        listed: list[tuple[Claim, str | None, str | None, str | None]] = []
        for row in rows:
            claim, first, other, last, trading, legal, assignee_name, _total = row
            parts = [first, other, last]
            customer_name = " ".join(part for part in parts if part) or None
            listed.append((claim, customer_name, trading or legal, assignee_name))
        return listed, total

    def _apply_queue(self, stmt: Select, queue: str) -> Select:
        mapping = {
            "vetting": ("VETTING", "CLAIM_SUBMITTED"),
            "information": ("ADDITIONAL_INFORMATION_REQUIRED",),
            "approval": ("VETTING_PASSED",),
            "definite": ("SENT_TO_DEFINITE", "DEFINITE_REVIEW"),
            "payment": (
                "PAYMENT_PENDING",
                "PAYMENT_AUTHORIZATION",
                "PAYMENT_AUTHORIZED",
                "PAYMENT_REVIEW",
            ),
            "payment_failed": ("PAYMENT_FAILED",),
            "high_value": None,
        }
        if queue == "intake":
            return stmt.where(
                Claim.channel == "GUEST",
                Claim.assigned_to_user_id.is_(None),
                Claim.status.in_(
                    ("CLAIM_SUBMITTED", "ADDITIONAL_INFORMATION_REQUIRED", "VETTING")
                ),
            )
        if queue == "high_value":
            return stmt.where(Claim.claimed_amount >= 250000)
        statuses = mapping.get(queue)
        if not statuses:
            return stmt.where(false())
        return stmt.where(Claim.status.in_(statuses))

    async def count_by_status(self) -> dict[str, int]:
        stmt = self._scope(select(Claim.status, func.count()).select_from(Claim)).group_by(
            Claim.status
        )
        rows = (await self.session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}

    async def desk_stats(self) -> dict[str, Any]:
        """Status + queue + assigned counts in one visibility-scoped statement."""
        assigned = Claim.assigned_to_user_id == self.ctx.user_id
        intake = and_(
            Claim.channel == "GUEST",
            Claim.assigned_to_user_id.is_(None),
            Claim.status.in_(
                ("CLAIM_SUBMITTED", "ADDITIONAL_INFORMATION_REQUIRED", "VETTING")
            ),
        )
        stmt = self._scope(
            select(
                Claim.status,
                func.count().label("n"),
                func.count().filter(assigned).label("assigned"),
                func.count().filter(intake).label("intake"),
                func.count()
                .filter(Claim.status.in_(("VETTING", "CLAIM_SUBMITTED")))
                .label("vetting"),
                func.count()
                .filter(Claim.status == "ADDITIONAL_INFORMATION_REQUIRED")
                .label("information"),
                func.count().filter(Claim.status == "VETTING_PASSED").label("approval"),
                func.count()
                .filter(Claim.status.in_(("SENT_TO_DEFINITE", "DEFINITE_REVIEW")))
                .label("definite"),
                func.count()
                .filter(
                    Claim.status.in_(
                        (
                            "PAYMENT_PENDING",
                            "PAYMENT_AUTHORIZATION",
                            "PAYMENT_AUTHORIZED",
                            "PAYMENT_REVIEW",
                        )
                    )
                )
                .label("payment"),
                func.count().filter(Claim.status == "PAYMENT_FAILED").label("payment_failed"),
                func.count().filter(Claim.claimed_amount >= 250000).label("high_value"),
            ).select_from(Claim)
        ).group_by(Claim.status)
        rows = (await self.session.execute(stmt)).all()
        status_counts: dict[str, int] = {}
        queue_counts = {
            "intake": 0,
            "vetting": 0,
            "information": 0,
            "approval": 0,
            "definite": 0,
            "payment": 0,
            "payment_failed": 0,
            "high_value": 0,
        }
        assigned_total = 0
        for row in rows:
            status_counts[str(row.status)] = int(row.n)
            assigned_total += int(row.assigned or 0)
            for key in queue_counts:
                queue_counts[key] += int(getattr(row, key) or 0)
        return {
            "status_counts": status_counts,
            "assigned_total": assigned_total,
            "queue_counts": queue_counts,
        }

    async def queue_previews(
        self, queues: list[str], *, limit: int = 8
    ) -> dict[str, list[Claim]]:
        """One statement: up to ``limit`` rows per desk queue."""
        if not queues:
            return {}
        parts = []
        for queue in queues:
            part = select(Claim.id, literal(queue).label("queue_name"))
            if not self.ctx.is_platform_admin:
                part = part.where(Claim.tenant_id == self.ctx.tenant_id)
            part = self._visibility_filter(self._apply_branch_scope(part))
            part = (
                self._apply_queue(part, queue)
                .order_by(Claim.updated_at.desc())
                .limit(limit)
            )
            parts.append(part)
        preview_stmt = parts[0] if len(parts) == 1 else union_all(*parts)
        id_rows = (await self.session.execute(preview_stmt)).all()
        ordered: dict[str, list[UUID]] = {queue: [] for queue in queues}
        wanted: set[UUID] = set()
        for claim_id, queue_name in id_rows:
            if queue_name in ordered:
                ordered[queue_name].append(claim_id)
                wanted.add(claim_id)
        if not wanted:
            return {queue: [] for queue in queues}
        found = {
            row.id: row
            for row in (
                await self.session.scalars(self._visibility_select().where(Claim.id.in_(wanted)))
            ).all()
        }
        return {
            queue: [found[cid] for cid in ids if cid in found]
            for queue, ids in ordered.items()
        }


class ClaimChildRepository:
    def __init__(self, session: AsyncSession, ctx: SecurityContext) -> None:
        self.session = session
        self.ctx = ctx

    def _tenant(self, model, claim_id: UUID):
        stmt = select(model).where(model.claim_id == claim_id)
        if not self.ctx.is_platform_admin:
            stmt = stmt.where(model.tenant_id == self.ctx.tenant_id)
        return stmt

    async def load_detail_collections(
        self,
        claim_id: UUID,
        *,
        include_internal_notes: bool,
        include_payments: bool,
    ) -> dict[str, list[Any]]:
        """Load every child collection the desk needs in one Postgres round-trip."""
        tenant_sql = "" if self.ctx.is_platform_admin else "AND tenant_id = CAST(:tid AS uuid)"
        notes_vis = "" if include_internal_notes else "AND visibility = 'CLIENT'"
        payments_sql = (
            f"""
            (
              SELECT coalesce(jsonb_agg(jsonb_build_object(
                'id', id::text,
                'amount', amount,
                'currency', currency,
                'beneficiary_type', beneficiary_type,
                'payment_status', payment_status,
                'provider_reference', provider_reference,
                'initiated_at', initiated_at,
                'completed_at', completed_at,
                'failure_reason', failure_reason
              ) ORDER BY created_at DESC), '[]'::jsonb)
              FROM claim_payments
              WHERE claim_id = CAST(:cid AS uuid) {tenant_sql}
            )
            """
            if include_payments
            else "'[]'::jsonb"
        )
        row = (
            await self.session.execute(
                text(
                    f"""
                    SELECT
                      (
                        SELECT coalesce(jsonb_agg(jsonb_build_object(
                          'id', id::text,
                          'visibility', visibility,
                          'body', body,
                          'created_at', created_at
                        ) ORDER BY created_at DESC), '[]'::jsonb)
                        FROM claim_notes
                        WHERE claim_id = CAST(:cid AS uuid) {tenant_sql} {notes_vis}
                      ) AS notes,
                      (
                        SELECT coalesce(jsonb_agg(jsonb_build_object(
                          'id', id::text,
                          'actor_type', actor_type,
                          'actor_display_name', actor_display_name,
                          'actor_role', actor_role,
                          'action', action,
                          'summary', summary,
                          'previous_state', previous_state,
                          'new_state', new_state,
                          'created_at', created_at,
                          'metadata', "metadata"
                        ) ORDER BY created_at DESC), '[]'::jsonb)
                        FROM claim_events
                        WHERE claim_id = CAST(:cid AS uuid) {tenant_sql}
                      ) AS timeline,
                      (
                        SELECT coalesce(jsonb_agg(jsonb_build_object(
                          'id', id::text,
                          'sequence', sequence,
                          'decision', decision,
                          'amount', amount,
                          'superseded', superseded,
                          'reason', reason,
                          'created_at', created_at,
                          'approver_user_id', approver_user_id::text
                        ) ORDER BY sequence ASC), '[]'::jsonb)
                        FROM claim_approvals
                        WHERE claim_id = CAST(:cid AS uuid) {tenant_sql}
                      ) AS approvals,
                      (
                        SELECT coalesce(jsonb_agg(jsonb_build_object(
                          'id', id::text,
                          'decision', decision,
                          'decision_reason', decision_reason,
                          'checklist', checklist,
                          'findings', findings,
                          'required_documents', required_documents,
                          'started_at', started_at,
                          'completed_at', completed_at,
                          'is_current', is_current
                        ) ORDER BY created_at DESC), '[]'::jsonb)
                        FROM claim_vettings
                        WHERE claim_id = CAST(:cid AS uuid) {tenant_sql}
                      ) AS vetting,
                      (
                        SELECT coalesce(jsonb_agg(jsonb_build_object(
                          'id', id::text,
                          'assigned_to_user_id', assigned_to_user_id::text,
                          'assigned_by_user_id', assigned_by_user_id::text,
                          'assigned_at', assigned_at,
                          'ended_at', ended_at,
                          'reason', reason
                        ) ORDER BY assigned_at DESC), '[]'::jsonb)
                        FROM claim_assignments
                        WHERE claim_id = CAST(:cid AS uuid) {tenant_sql}
                      ) AS assignments,
                      (
                        SELECT coalesce(jsonb_agg(jsonb_build_object(
                          'id', id::text,
                          'provider', provider,
                          'external_reference', external_reference,
                          'status', status,
                          'decision', decision,
                          'submitted_at', submitted_at,
                          'response_received_at', response_received_at,
                          'approved_amount', approved_amount
                        ) ORDER BY created_at DESC), '[]'::jsonb)
                        FROM claim_external_reviews
                        WHERE claim_id = CAST(:cid AS uuid) {tenant_sql}
                      ) AS definite_reviews,
                      (
                        SELECT coalesce(jsonb_agg(jsonb_build_object(
                          'id', id::text,
                          'followup_type', followup_type,
                          'subject', subject,
                          'message', message,
                          'status', status,
                          'due_at', due_at,
                          'completed_at', completed_at,
                          'created_at', created_at
                        ) ORDER BY created_at DESC), '[]'::jsonb)
                        FROM claim_followups
                        WHERE claim_id = CAST(:cid AS uuid) {tenant_sql}
                      ) AS followups,
                      (
                        SELECT coalesce(jsonb_agg(jsonb_build_object(
                          'id', id::text,
                          'kind', kind,
                          'original_filename', original_filename,
                          'content_type', content_type,
                          'file_size_bytes', file_size_bytes,
                          'created_at', created_at
                        ) ORDER BY created_at DESC), '[]'::jsonb)
                        FROM claim_documents
                        WHERE claim_id = CAST(:cid AS uuid)
                          AND deleted_at IS NULL
                          {tenant_sql}
                      ) AS documents,
                      (
                        SELECT coalesce(jsonb_agg(jsonb_build_object(
                          'id', id::text,
                          'field_name', field_name,
                          'previous_value', previous_value,
                          'proposed_value', proposed_value,
                          'status', status,
                          'reason', reason,
                          'created_at', created_at
                        ) ORDER BY created_at DESC), '[]'::jsonb)
                        FROM claim_amendments
                        WHERE claim_id = CAST(:cid AS uuid) {tenant_sql}
                      ) AS amendments,
                      {payments_sql} AS payments
                    """
                ),
                {
                    "cid": str(claim_id),
                    "tid": str(self.ctx.tenant_id),
                },
            )
        ).one()
        return {
            "notes": _json_list(row.notes),
            "timeline": _json_list(row.timeline),
            "approvals": _json_list(row.approvals),
            "vetting": _json_list(row.vetting),
            "assignments": _json_list(row.assignments),
            "definite_reviews": _json_list(row.definite_reviews),
            "followups": _json_list(row.followups),
            "documents": _json_list(row.documents),
            "amendments": _json_list(row.amendments),
            "payments": _json_list(row.payments),
        }

    async def open_assignments(self, claim_id: UUID) -> list[ClaimAssignment]:
        return list(
            (
                await self.session.scalars(
                    self._tenant(ClaimAssignment, claim_id).where(
                        ClaimAssignment.ended_at.is_(None)
                    )
                )
            ).all()
        )

    async def current_vetting(self, claim_id: UUID) -> ClaimVetting | None:
        return await self.session.scalar(
            self._tenant(ClaimVetting, claim_id)
            .where(ClaimVetting.is_current.is_(True))
            .order_by(ClaimVetting.created_at.desc())
        )

    async def vettings(self, claim_id: UUID) -> list[ClaimVetting]:
        return list(
            (
                await self.session.scalars(
                    self._tenant(ClaimVetting, claim_id).order_by(ClaimVetting.created_at.desc())
                )
            ).all()
        )

    async def assignments(self, claim_id: UUID) -> list[ClaimAssignment]:
        return list(
            (
                await self.session.scalars(
                    self._tenant(ClaimAssignment, claim_id).order_by(
                        ClaimAssignment.assigned_at.desc()
                    )
                )
            ).all()
        )

    async def reviews(self, claim_id: UUID) -> list[ClaimExternalReview]:
        return list(
            (
                await self.session.scalars(
                    self._tenant(ClaimExternalReview, claim_id).order_by(
                        ClaimExternalReview.created_at.desc()
                    )
                )
            ).all()
        )

    async def latest_review(self, claim_id: UUID) -> ClaimExternalReview | None:
        return await self.session.scalar(
            self._tenant(ClaimExternalReview, claim_id).order_by(
                ClaimExternalReview.created_at.desc()
            )
        )

    async def review_by_reference(
        self, *, provider: str, external_reference: str
    ) -> ClaimExternalReview | None:
        return await self.session.scalar(
            select(ClaimExternalReview).where(
                ClaimExternalReview.provider == provider,
                ClaimExternalReview.external_reference == external_reference,
            )
        )

    async def approvals(self, claim_id: UUID) -> list[ClaimApproval]:
        return list(
            (
                await self.session.scalars(
                    self._tenant(ClaimApproval, claim_id).order_by(ClaimApproval.sequence.asc())
                )
            ).all()
        )

    async def payments(self, claim_id: UUID) -> list[ClaimPayment]:
        return list(
            (
                await self.session.scalars(
                    self._tenant(ClaimPayment, claim_id).order_by(ClaimPayment.created_at.desc())
                )
            ).all()
        )

    async def active_payment(self, claim_id: UUID) -> ClaimPayment | None:
        return await self.session.scalar(
            self._tenant(ClaimPayment, claim_id).where(
                ClaimPayment.payment_status.in_(
                    (
                        "DRAFT",
                        "PENDING_AUTHORIZATION",
                        "AUTHORIZED",
                        "PROCESSING",
                    )
                )
            )
        )

    async def payment_by_idempotency(self, key: str) -> ClaimPayment | None:
        stmt = select(ClaimPayment).where(ClaimPayment.idempotency_key == key)
        if not self.ctx.is_platform_admin:
            stmt = stmt.where(ClaimPayment.tenant_id == self.ctx.tenant_id)
        return await self.session.scalar(stmt)

    async def payment_by_provider_reference(self, reference: str) -> ClaimPayment | None:
        return await self.session.scalar(
            select(ClaimPayment).where(ClaimPayment.provider_reference == reference)
        )

    async def notes(self, claim_id: UUID, *, include_internal: bool) -> list[ClaimNote]:
        stmt = self._tenant(ClaimNote, claim_id)
        if not include_internal:
            stmt = stmt.where(ClaimNote.visibility == "CLIENT")
        return list(
            (await self.session.scalars(stmt.order_by(ClaimNote.created_at.desc()))).all()
        )

    async def followups(self, claim_id: UUID) -> list[ClaimFollowup]:
        return list(
            (
                await self.session.scalars(
                    self._tenant(ClaimFollowup, claim_id).order_by(ClaimFollowup.created_at.desc())
                )
            ).all()
        )

    async def open_followups(self, claim_id: UUID) -> list[ClaimFollowup]:
        return list(
            (
                await self.session.scalars(
                    self._tenant(ClaimFollowup, claim_id)
                    .where(
                        ClaimFollowup.status.in_(("OPEN", "PENDING_CLIENT", "PENDING_INTERNAL"))
                    )
                    .order_by(ClaimFollowup.created_at.desc())
                )
            ).all()
        )

    async def documents(self, claim_id: UUID) -> list[ClaimDocument]:
        return list(
            (
                await self.session.scalars(
                    self._tenant(ClaimDocument, claim_id)
                    .where(ClaimDocument.deleted_at.is_(None))
                    .order_by(ClaimDocument.created_at.desc())
                )
            ).all()
        )

    async def document(self, document_id: UUID) -> ClaimDocument | None:
        stmt = select(ClaimDocument).where(
            ClaimDocument.id == document_id,
            ClaimDocument.deleted_at.is_(None),
        )
        if not self.ctx.is_platform_admin:
            stmt = stmt.where(ClaimDocument.tenant_id == self.ctx.tenant_id)
        return await self.session.scalar(stmt)

    async def document_by_sha256(
        self, claim_id: UUID, content_sha256: str
    ) -> ClaimDocument | None:
        digest = (content_sha256 or "").strip().lower()
        if len(digest) != 64:
            return None
        stmt = (
            self._tenant(ClaimDocument, claim_id)
            .where(
                ClaimDocument.deleted_at.is_(None),
                ClaimDocument.content_sha256 == digest,
            )
            .order_by(ClaimDocument.created_at.asc())
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def events(self, claim_id: UUID) -> list[ClaimEvent]:
        return list(
            (
                await self.session.scalars(
                    self._tenant(ClaimEvent, claim_id).order_by(ClaimEvent.created_at.desc())
                )
            ).all()
        )

    async def latest_actor_action(
        self,
        claim_id: UUID,
        *,
        action: str,
        user_id: UUID | None,
    ) -> ClaimEvent | None:
        stmt = (
            self._tenant(ClaimEvent, claim_id)
            .where(ClaimEvent.action == action)
            .order_by(ClaimEvent.created_at.desc())
            .limit(1)
        )
        if user_id is not None:
            stmt = stmt.where(ClaimEvent.actor_user_id == user_id)
        return await self.session.scalar(stmt)

    async def amendments(self, claim_id: UUID) -> list[ClaimAmendment]:
        return list(
            (
                await self.session.scalars(
                    self._tenant(ClaimAmendment, claim_id).order_by(
                        ClaimAmendment.created_at.desc()
                    )
                )
            ).all()
        )

    async def open_amendment(self, claim_id: UUID) -> ClaimAmendment | None:
        return await self.session.scalar(
            self._tenant(ClaimAmendment, claim_id).where(
                ClaimAmendment.status.in_(("REQUESTED", "IN_REVIEW"))
            )
        )

    async def approval_policies(self) -> list[ApprovalPolicy]:
        return list(
            (
                await self.session.scalars(
                    select(ApprovalPolicy).where(
                        ApprovalPolicy.tenant_id == self.ctx.tenant_id,
                        ApprovalPolicy.active.is_(True),
                    )
                )
            ).all()
        )

    async def segregation_policies(self) -> list[SegregationPolicy]:
        return list(
            (
                await self.session.scalars(
                    select(SegregationPolicy).where(
                        SegregationPolicy.tenant_id == self.ctx.tenant_id,
                        SegregationPolicy.active.is_(True),
                    )
                )
            ).all()
        )
