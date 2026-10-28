"""Wallet HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db, require_permissions
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.modules.payments.schemas import WalletPublic, WalletTopUpRequest, WalletTxnPublic
from app.modules.wallets.service import WalletService, txn_to_public, wallet_to_public

router = APIRouter(prefix="/wallets", tags=["Wallets"])


@router.get("/me")
async def get_wallet(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("wallet:read"))],
) -> dict:
    service = WalletService(db, ctx)
    wallet = await service.get_or_create()
    await db.commit()
    return success_response(
        WalletPublic.model_validate(wallet_to_public(wallet)).model_dump(mode="json"),
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/me/transactions")
async def list_wallet_transactions(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("wallet:read"))],
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict:
    service = WalletService(db, ctx)
    wallet, rows, total = await service.list_transactions(page=page, limit=limit)
    await db.commit()
    return success_response(
        {
            "wallet": WalletPublic.model_validate(wallet_to_public(wallet)).model_dump(mode="json"),
            "items": [
                WalletTxnPublic.model_validate(txn_to_public(r)).model_dump(mode="json")
                for r in rows
            ],
            "page": page,
            "limit": limit,
            "total": total,
        },
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/me/top-up")
async def top_up_wallet(
    body: WalletTopUpRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("wallet:topup"))],
) -> dict:
    service = WalletService(db, ctx)
    wallet = await service.top_up(amount=body.amount, description=body.description)
    await db.commit()
    return success_response(
        WalletPublic.model_validate(wallet_to_public(wallet)).model_dump(mode="json"),
        message="Wallet topped up",
        request_id=getattr(request.state, "request_id", None),
    )
