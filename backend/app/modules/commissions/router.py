"""Commission HTTP routes."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db, require_permissions
from app.core.exceptions import ValidationAppError
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.modules.commissions.schemas import (
    CommissionAccountSummary,
    CommissionLedgerEntryPublic,
    CommissionPayoutRequest,
    CommissionSettingsPublic,
    CommissionSettingsUpdateRequest,
    CommissionStatementPublic,
)
from app.modules.commissions.service import CommissionService, entry_public, settings_public

router = APIRouter(prefix="/commissions", tags=["Commissions"])

_COMMISSION_READ = (
    "commission:read",
    "commission:manage",
    "settings:manage",
    "tenant:manage",
)
_COMMISSION_WRITE = ("commission:manage", "settings:manage")


@router.get("/settings")
async def get_commission_settings(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext,
        Depends(require_permissions(*_COMMISSION_READ)),
    ],
) -> dict:
    service = CommissionService(db, ctx)
    row = await service.get_or_create_settings()
    await db.commit()
    return success_response(
        CommissionSettingsPublic.model_validate(settings_public(row)).model_dump(mode="json"),
        request_id=getattr(request.state, "request_id", None),
    )


@router.put("/settings")
async def update_commission_settings(
    body: CommissionSettingsUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext, Depends(require_permissions(*_COMMISSION_WRITE))
    ],
) -> dict:
    service = CommissionService(db, ctx)
    row = await service.update_settings(body)
    await db.commit()
    return success_response(
        CommissionSettingsPublic.model_validate(settings_public(row)).model_dump(mode="json"),
        message="Commission settings saved",
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/accounts")
async def list_commission_accounts(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext,
        Depends(require_permissions(*_COMMISSION_READ)),
    ],
) -> dict:
    service = CommissionService(db, ctx)
    items = await service.list_accounts()
    return success_response(
        {
            "items": [
                CommissionAccountSummary.model_validate(row).model_dump(mode="json")
                for row in items
            ]
        },
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/ledger")
async def list_commission_ledger(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext,
        Depends(require_permissions(*_COMMISSION_READ)),
    ],
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    q: Annotated[str | None, Query(max_length=128)] = None,
    entry_kind: Annotated[str | None, Query(max_length=16)] = None,
    intermediary_id: Annotated[str | None, Query(max_length=36)] = None,
    house: Annotated[bool, Query()] = False,
) -> dict:
    service = CommissionService(db, ctx)
    agent_id: UUID | None = None
    if intermediary_id and not house:
        try:
            agent_id = UUID(intermediary_id)
        except ValueError as exc:
            raise ValidationAppError("intermediary_id must be a valid UUID") from exc
    rows, total = await service.list_entries(
        page=page,
        limit=limit,
        intermediary_id=agent_id,
        house_only=house,
        query=q,
        entry_kind=entry_kind,
    )
    return success_response(
        {
            "items": [
                CommissionLedgerEntryPublic.model_validate(entry_public(r)).model_dump(mode="json")
                for r in rows
            ],
            "page": page,
            "limit": limit,
            "total": total,
        },
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/statement")
async def commission_statement(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext,
        Depends(require_permissions(*_COMMISSION_READ)),
    ],
    intermediary_id: Annotated[str | None, Query(max_length=36)] = None,
    house: Annotated[bool, Query()] = False,
    period_start: Annotated[datetime | None, Query()] = None,
    period_end: Annotated[datetime | None, Query()] = None,
) -> dict:
    service = CommissionService(db, ctx)
    agent_id: UUID | None = None
    if intermediary_id and not house:
        try:
            agent_id = UUID(intermediary_id)
        except ValueError as exc:
            raise ValidationAppError("intermediary_id must be a valid UUID") from exc
    data = await service.statement(
        intermediary_id=agent_id,
        house=house,
        period_start=period_start,
        period_end=period_end,
    )
    return success_response(
        CommissionStatementPublic.model_validate(data).model_dump(mode="json"),
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/payouts")
async def record_commission_payout(
    body: CommissionPayoutRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("commission:payout"))],
) -> dict:
    service = CommissionService(db, ctx)
    agent_id: UUID | None = None
    if body.intermediary_id and not body.house:
        try:
            agent_id = UUID(body.intermediary_id)
        except ValueError as exc:
            raise ValidationAppError("intermediary_id must be a valid UUID") from exc
    if not body.house and agent_id is None:
        raise ValidationAppError("Select an agent account or house payout")
    row = await service.record_payout(
        intermediary_id=agent_id,
        house=body.house,
        note=body.note,
    )
    await db.commit()
    return success_response(
        CommissionLedgerEntryPublic.model_validate(entry_public(row)).model_dump(mode="json"),
        message="Commission payout recorded",
        request_id=getattr(request.state, "request_id", None),
    )
