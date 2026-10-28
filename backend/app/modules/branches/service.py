"""Branch directory — create and maintain agency locations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationAppError
from app.core.security.context import SecurityContext
from app.core.validation.identity import normalize_phone
from app.modules.audit.service import AuditService
from app.modules.branches.repository import BranchRepository
from app.modules.branches.schemas import BranchCreateRequest, BranchUpdateRequest
from app.modules.tenants.models import Branch


def to_public(branch: Branch, *, users_count: int = 0) -> dict:
    return {
        "id": str(branch.id),
        "name": branch.name,
        "code": branch.code,
        "status": branch.status,
        "phone": branch.phone,
        "email": branch.email,
        "city": branch.city,
        "address_line": branch.address_line,
        "users_count": users_count,
        "created_at": branch.created_at,
        "updated_at": branch.updated_at,
    }


class BranchService:
    def __init__(self, session: AsyncSession, ctx: SecurityContext) -> None:
        self.session = session
        self.ctx = ctx
        self.repo = BranchRepository(session, ctx)
        self.audit = AuditService(session)

    async def list_public(
        self, *, page: int, limit: int, query: str | None
    ) -> tuple[list[dict], int]:
        rows, total = await self.repo.search(
            query=query,
            offset=(page - 1) * limit,
            limit=limit,
        )
        return [to_public(branch, users_count=count) for branch, count in rows], total

    async def create(self, body: BranchCreateRequest) -> dict:
        self.ctx.require_active_tenant()
        code = body.code.upper() if body.code else None
        if code and await self.repo.find_by_code(code):
            raise ConflictError("A branch with this code already exists")
        phone = normalize_phone(body.phone) if body.phone and body.phone.strip() else None
        branch = Branch(
            tenant_id=self.ctx.tenant_id,
            name=body.name,
            code=code,
            status="ACTIVE",
            phone=phone,
            email=str(body.email).lower() if body.email else None,
            city=body.city,
            address_line=body.address_line,
        )
        await self.repo.add(branch)
        await self.session.flush()
        await self.audit.record(
            action="branch.create",
            resource="branch",
            resource_id=str(branch.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            metadata={"name": branch.name, "code": branch.code},
        )
        return to_public(branch)

    async def update(self, branch_id: UUID, body: BranchUpdateRequest) -> dict:
        self.ctx.require_active_tenant()
        branch = await self.repo.get_active_by_id(branch_id)
        if body.name is not None:
            branch.name = body.name
        if body.code is not None:
            code = body.code.upper()
            existing = await self.repo.find_by_code(code)
            if existing is not None and existing.id != branch.id:
                raise ConflictError("A branch with this code already exists")
            branch.code = code
        if body.phone is not None:
            branch.phone = normalize_phone(body.phone) if body.phone.strip() else None
        if body.email is not None:
            branch.email = str(body.email).lower()
        if body.city is not None:
            branch.city = body.city
        if body.address_line is not None:
            branch.address_line = body.address_line
        if body.status is not None:
            if body.status == "DISABLED" and branch.status == "ACTIVE":
                await self._assert_not_last_active(branch.id)
            branch.status = body.status
        await self.session.flush()
        await self.audit.record(
            action="branch.update",
            resource="branch",
            resource_id=str(branch.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            metadata={"status": branch.status},
        )
        return to_public(branch)

    async def _assert_not_last_active(self, branch_id: UUID) -> None:
        rows, _ = await self.repo.search(query=None, offset=0, limit=200)
        active = [branch for branch, _ in rows if branch.status == "ACTIVE" and branch.id != branch_id]
        if not active:
            raise ValidationAppError("Keep at least one active branch")
