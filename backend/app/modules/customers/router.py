"""Customer HTTP routes — thin controllers."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db, require_permissions
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.modules.customers.schemas import (
    CustomerAssignRequest,
    CustomerCreateRequest,
    CustomerPublic,
    CustomerUpdateRequest,
)
from app.modules.customers.service import CustomerService, to_public

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.post("")
async def create_customer(
    body: CustomerCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("customer:create"))],
) -> dict:
    service = CustomerService(db, ctx)
    customer = await service.create(body)
    await db.commit()
    return success_response(
        CustomerPublic.model_validate(to_public(customer)).model_dump(mode="json"),
        message="Customer created",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.get("")
async def list_customers(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("customer:read"))],
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    q: Annotated[str | None, Query(max_length=128)] = None,
) -> dict:
    service = CustomerService(db, ctx)
    items, total = await service.list_public(page=page, limit=limit, query=q)
    return success_response(
        {
            "items": [
                CustomerPublic.model_validate(item).model_dump(mode="json") for item in items
            ],
            "page": page,
            "limit": limit,
            "total": total,
        },
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.get("/lookup")
async def lookup_customer_by_id_number(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("customer:read"))],
    id_number: Annotated[str, Query(min_length=5, max_length=32)],
) -> dict:
    """Local CRM lookup by national ID / passport (staff rows only)."""
    service = CustomerService(db, ctx)
    customer = await service.lookup_by_id_number(id_number)
    return success_response(
        {
            "found": customer is not None,
            "customer": (
                CustomerPublic.model_validate(to_public(customer)).model_dump(mode="json")
                if customer
                else None
            ),
            "last_vehicle": await service.last_vehicle(customer) if customer else None,
        },
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.get("/{customer_id}")
async def get_customer(
    customer_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("customer:read"))],
) -> dict:
    service = CustomerService(db, ctx)
    customer = await service.get(customer_id)
    return success_response(
        CustomerPublic.model_validate(to_public(customer)).model_dump(mode="json"),
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.post("/{customer_id}/documents")
async def upload_customer_document(
    customer_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext,
        Depends(require_permissions("customer:update", "proposal:create")),
    ],
    kind: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> dict:
    """Upload logbook / national ID scans for a customer (quote KYC)."""
    payload = await file.read()
    service = CustomerService(db, ctx)
    data = await service.upload_kyc_document(
        customer_id,
        kind=(kind or "").strip().lower(),
        payload=payload,
        filename=file.filename or "document",
    )
    await db.commit()
    return success_response(
        {
            "kind": data["kind"],
            "url": data["url"],
            "customer": CustomerPublic.model_validate(data["customer"]).model_dump(
                mode="json"
            ),
        },
        message="Document uploaded",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.patch("/{customer_id}")
async def update_customer(
    customer_id: UUID,
    body: CustomerUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("customer:update"))],
) -> dict:
    service = CustomerService(db, ctx)
    customer = await service.update(customer_id, body)
    await db.commit()
    return success_response(
        CustomerPublic.model_validate(to_public(customer)).model_dump(mode="json"),
        message="Customer updated",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.delete("/{customer_id}")
async def delete_customer(
    customer_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("customer:delete"))],
) -> dict:
    service = CustomerService(db, ctx)
    await service.soft_delete(customer_id)
    await db.commit()
    return success_response(
        message="Customer deleted",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.post("/{customer_id}/assign")
async def assign_customer(
    customer_id: UUID,
    body: CustomerAssignRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("customer:update"))],
) -> dict:
    service = CustomerService(db, ctx)
    assigned = UUID(body.assigned_user_id) if body.assigned_user_id else None
    customer = await service.assign(customer_id, assigned)
    await db.commit()
    return success_response(
        CustomerPublic.model_validate(to_public(customer)).model_dump(mode="json"),
        message="Customer assignment updated",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )
