"""Reference data service — platform catalog + tenant overlays, Redis cache."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.security.context import SecurityContext
from app.modules.audit.service import AuditService
from app.modules.products.cache import (
    MAKES_TTL_SECONDS,
    PRODUCTS_TTL_SECONDS,
    REASONS_TTL_SECONDS,
    ReferenceDataCache,
)
from app.modules.products.models import CancellationReason, InsuranceProduct, VehicleMake
from app.modules.products.schemas import ProductCreateRequest, VehicleMakeCreateRequest


def _product_public(row: InsuranceProduct) -> dict:
    return {
        "id": str(row.id),
        "code": row.code,
        "name": row.name,
        "description": row.description,
        "cover_options": row.cover_options or [],
        "is_active": row.is_active,
        "scope": "TENANT" if row.tenant_id else "PLATFORM",
        "provider_code": row.provider_code,
        "synced_at": row.synced_at,
    }


def _make_public(row: VehicleMake) -> dict:
    return {
        "id": str(row.id),
        "code": row.code,
        "name": row.name,
        "is_active": row.is_active,
        "sort_order": row.sort_order,
        "scope": "TENANT" if row.tenant_id else "PLATFORM",
        "provider_code": row.provider_code,
    }


def _reason_public(row: CancellationReason) -> dict:
    return {
        "id": str(row.id),
        "code": row.code,
        "label": row.label,
        "is_active": row.is_active,
        "scope": "TENANT" if row.tenant_id else "PLATFORM",
    }


class ProductService:
    def __init__(
        self,
        session: AsyncSession,
        ctx: SecurityContext,
        cache: ReferenceDataCache | None = None,
    ) -> None:
        self.session = session
        self.ctx = ctx
        self.cache = cache or ReferenceDataCache()
        self.audit = AuditService(session)

    async def list_products(self) -> list[dict]:
        tenant_key = str(self.ctx.tenant_id)
        cached = await self.cache.get_json("products", tenant_key)
        if cached is not None:
            return cached

        stmt = (
            select(InsuranceProduct)
            .where(
                InsuranceProduct.is_active.is_(True),
                or_(
                    InsuranceProduct.tenant_id.is_(None),
                    InsuranceProduct.tenant_id == self.ctx.tenant_id,
                ),
            )
            .order_by(InsuranceProduct.name.asc())
        )
        rows = list((await self.session.scalars(stmt)).all())
        # Prefer tenant overlay over platform duplicate codes
        by_code: dict[str, InsuranceProduct] = {}
        for row in rows:
            if row.code not in by_code or row.tenant_id is not None:
                by_code[row.code] = row
        payload = [_product_public(r) for r in by_code.values()]
        payload.sort(key=lambda x: x["name"])
        await self.cache.set_json("products", tenant_key, payload, PRODUCTS_TTL_SECONDS)
        return payload

    async def list_makes(self) -> list[dict]:
        tenant_key = str(self.ctx.tenant_id)
        cached = await self.cache.get_json("makes", tenant_key)
        if cached is not None:
            return cached

        stmt = (
            select(VehicleMake)
            .where(
                VehicleMake.is_active.is_(True),
                or_(
                    VehicleMake.tenant_id.is_(None),
                    VehicleMake.tenant_id == self.ctx.tenant_id,
                ),
            )
            .order_by(VehicleMake.sort_order.asc(), VehicleMake.name.asc())
        )
        rows = list((await self.session.scalars(stmt)).all())
        by_code: dict[str, VehicleMake] = {}
        for row in rows:
            if row.code not in by_code or row.tenant_id is not None:
                by_code[row.code] = row
        payload = [_make_public(r) for r in by_code.values()]
        payload.sort(key=lambda x: (x["sort_order"], x["name"]))
        await self.cache.set_json("makes", tenant_key, payload, MAKES_TTL_SECONDS)
        return payload

    async def list_cancellation_reasons(self) -> list[dict]:
        tenant_key = str(self.ctx.tenant_id)
        cached = await self.cache.get_json("cancel_reasons", tenant_key)
        if cached is not None:
            return cached

        stmt = (
            select(CancellationReason)
            .where(
                CancellationReason.is_active.is_(True),
                or_(
                    CancellationReason.tenant_id.is_(None),
                    CancellationReason.tenant_id == self.ctx.tenant_id,
                ),
            )
            .order_by(CancellationReason.label.asc())
        )
        rows = list((await self.session.scalars(stmt)).all())
        by_code: dict[str, CancellationReason] = {}
        for row in rows:
            if row.code not in by_code or row.tenant_id is not None:
                by_code[row.code] = row
        payload = [_reason_public(r) for r in by_code.values()]
        await self.cache.set_json(
            "cancel_reasons", tenant_key, payload, REASONS_TTL_SECONDS
        )
        return payload

    async def create_tenant_product(self, body: ProductCreateRequest) -> InsuranceProduct:
        self.ctx.require_active_tenant()
        code = body.code.strip().upper()
        existing = await self.session.scalar(
            select(InsuranceProduct).where(
                InsuranceProduct.tenant_id == self.ctx.tenant_id,
                InsuranceProduct.code == code,
            )
        )
        if existing:
            raise ConflictError("Product code already exists for this tenant")
        row = InsuranceProduct(
            tenant_id=self.ctx.tenant_id,
            code=code,
            name=body.name.strip(),
            description=body.description,
            cover_options=body.cover_options,
            is_active=True,
            provider_code=body.provider_code,
            metadata_json={},
        )
        self.session.add(row)
        await self.session.flush()
        await self.cache.invalidate("products", str(self.ctx.tenant_id))
        await self.audit.record(
            action="product.create",
            resource="insurance_product",
            resource_id=str(row.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            metadata={"code": row.code},
        )
        return row

    async def create_tenant_make(self, body: VehicleMakeCreateRequest) -> VehicleMake:
        self.ctx.require_active_tenant()
        code = body.code.strip().upper()
        existing = await self.session.scalar(
            select(VehicleMake).where(
                VehicleMake.tenant_id == self.ctx.tenant_id,
                VehicleMake.code == code,
            )
        )
        if existing:
            raise ConflictError("Vehicle make code already exists for this tenant")
        row = VehicleMake(
            tenant_id=self.ctx.tenant_id,
            code=code,
            name=body.name.strip(),
            sort_order=body.sort_order,
            is_active=True,
        )
        self.session.add(row)
        await self.session.flush()
        await self.cache.invalidate("makes", str(self.ctx.tenant_id))
        await self.audit.record(
            action="vehicle_make.create",
            resource="vehicle_make",
            resource_id=str(row.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            metadata={"code": row.code},
        )
        return row
