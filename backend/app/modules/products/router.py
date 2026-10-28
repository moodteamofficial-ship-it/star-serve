"""Insurance products and vehicle reference routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.redis_client import get_redis_client
from app.core.dependencies.auth import get_db, require_permissions
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.modules.products.cache import ReferenceDataCache
from app.modules.products.schemas import (
    CancellationReasonPublic,
    ProductCreateRequest,
    ProductPublic,
    VehicleMakeCreateRequest,
    VehicleMakePublic,
)
from app.modules.products.service import ProductService, _make_public, _product_public

router = APIRouter(tags=["Insurance Products"])


def _cache() -> ReferenceDataCache:
    return ReferenceDataCache(get_redis_client())


@router.get("/products")
async def list_products(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("product:read"))],
) -> dict:
    service = ProductService(db, ctx, _cache())
    items = await service.list_products()
    return success_response(
        [ProductPublic.model_validate(i).model_dump(mode="json") for i in items],
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.post("/products")
async def create_product(
    body: ProductCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("product:manage"))],
) -> dict:
    service = ProductService(db, ctx, _cache())
    row = await service.create_tenant_product(body)
    await db.commit()
    return success_response(
        ProductPublic.model_validate(_product_public(row)).model_dump(mode="json"),
        message="Product created",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.get("/vehicle-makes")
async def list_vehicle_makes(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("product:read"))],
) -> dict:
    service = ProductService(db, ctx, _cache())
    items = await service.list_makes()
    return success_response(
        [VehicleMakePublic.model_validate(i).model_dump(mode="json") for i in items],
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.post("/vehicle-makes")
async def create_vehicle_make(
    body: VehicleMakeCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("product:manage"))],
) -> dict:
    service = ProductService(db, ctx, _cache())
    row = await service.create_tenant_make(body)
    await db.commit()
    return success_response(
        VehicleMakePublic.model_validate(_make_public(row)).model_dump(mode="json"),
        message="Vehicle make created",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.get("/cancellation-reasons")
async def list_cancellation_reasons(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("product:read"))],
) -> dict:
    service = ProductService(db, ctx, _cache())
    items = await service.list_cancellation_reasons()
    return success_response(
        [CancellationReasonPublic.model_validate(i).model_dump(mode="json") for i in items],
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )
