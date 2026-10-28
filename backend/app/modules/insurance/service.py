"""Insurance orchestration — provider adapter + local tenant records + jobs."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.enums import JobStatus, JobType
from app.core.exceptions import ValidationAppError
from app.core.security.context import SecurityContext
from app.core.validation.identity import normalize_id_number, normalize_kra_pin, normalize_phone
from app.integrations.insurance.ports import InsuranceProvider
from app.modules.audit.service import AuditService
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.schemas import CustomerCreateRequest
from app.modules.customers.service import CustomerService, to_public as customer_to_public
from app.modules.intermediaries.repository import IntermediaryRepository
from app.modules.intermediaries.schemas import IntermediaryCreateRequest
from app.modules.intermediaries.service import IntermediaryService, to_public as intermediary_to_public
from app.modules.jobs.service import JobService
from app.modules.insurance.schemas import (
    EnsureClientRequest,
    EnsureIntermediaryRequest,
    PremiumCalculateRequest,
)
from app.modules.products.cache import ReferenceDataCache
from app.modules.products.models import CancellationReason, InsuranceProduct, VehicleMake


class InsuranceOrchestrationService:
    def __init__(
        self,
        session: AsyncSession,
        ctx: SecurityContext,
        provider: InsuranceProvider,
        cache: ReferenceDataCache | None = None,
    ) -> None:
        self.session = session
        self.ctx = ctx
        self.provider = provider
        self.cache = cache or ReferenceDataCache()
        self.audit = AuditService(session)
        self.jobs = JobService(session, ctx)

    async def check_client(self, id_number: str) -> dict:
        self.ctx.require_staff_principal()
        self.ctx.require_active_tenant()
        normalized = normalize_id_number(id_number)
        job = await self.jobs.create(
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            job_type=JobType.CLIENT_CHECK,
        )
        await self.jobs.add_event(job, "EXTERNAL_REQUEST_STARTED", message="checkClient")
        remote = await self.provider.check_client(id_number=normalized)
        await self.jobs.add_event(
            job,
            "EXTERNAL_RESPONSE_RECEIVED",
            message="checkClient",
            metadata={"found": remote is not None},
        )
        local_repo = CustomerRepository(self.session, self.ctx)
        local = await local_repo.find_by_id_number(normalized)
        await self.jobs.transition(job, JobStatus.COMPLETED)
        await self.audit.record(
            action="insurance.client_check",
            resource="customer",
            resource_id=str(local.id) if local else None,
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            metadata={"id_number": normalized, "provider_found": remote is not None},
        )
        return {
            "job_id": job.job_key,
            "id_number": normalized,
            "provider": remote,
            "local": customer_to_public(local) if local else None,
        }

    async def ensure_client(self, body: EnsureClientRequest) -> dict:
        self.ctx.require_staff_principal()
        self.ctx.require_active_tenant()
        normalized = normalize_id_number(body.id_number)
        job = await self.jobs.create(
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            job_type=JobType.CLIENT_CREATION,
        )

        await self.jobs.add_event(job, "EXTERNAL_REQUEST_STARTED", message="checkClient")
        remote = await self.provider.check_client(id_number=normalized)
        await self.jobs.add_event(
            job,
            "EXTERNAL_RESPONSE_RECEIVED",
            metadata={"found": remote is not None},
        )

        if remote is None and body.create_if_missing:
            await self.jobs.add_event(job, "EXTERNAL_REQUEST_STARTED", message="createClient")
            remote = await self.provider.create_client(
                {
                    "first_name": body.first_name,
                    "last_name": body.last_name,
                    "other_names": body.other_names,
                    "id_number": normalized,
                    "kra_pin": normalize_kra_pin(body.kra_pin),
                    "phone": normalize_phone(body.phone),
                    "email": str(body.email).lower() if body.email else None,
                }
            )
            await self.jobs.add_event(job, "EXTERNAL_RESPONSE_RECEIVED", message="createClient")

        customers = CustomerService(self.session, self.ctx)
        local_repo = CustomerRepository(self.session, self.ctx)
        local = await local_repo.find_by_id_number(normalized)
        if local is None:
            local = await customers.create(
                CustomerCreateRequest(
                    first_name=body.first_name,
                    last_name=body.last_name,
                    other_names=body.other_names,
                    id_number=normalized,
                    kra_pin=body.kra_pin,
                    phone=body.phone,
                    email=body.email,
                )
            )
        if remote and remote.get("external_ref"):
            local.external_client_ref = str(remote["external_ref"])
        # Persist full provider check/create payload for audit & re-open with customer
        if remote is not None:
            existing = dict(local.provider_payload) if isinstance(local.provider_payload, dict) else {}
            local.provider_payload = {
                **existing,
                "ensure_client": remote if isinstance(remote, dict) else {"data": remote},
                "ensure_client_at": datetime.now(UTC).isoformat(),
                "ensure_client_job_id": job.job_key,
            }
            local.last_issuance_job_id = job.job_key
        await self.session.flush()

        await self.jobs.transition(job, JobStatus.COMPLETED)
        await self.audit.record(
            action="insurance.client_ensure",
            resource="customer",
            resource_id=str(local.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            metadata={"id_number": normalized},
        )
        return {
            "job_id": job.job_key,
            "provider": remote,
            "local": customer_to_public(local),
        }

    async def check_intermediary(self, identification: str) -> dict:
        self.ctx.require_staff_principal()
        self.ctx.require_active_tenant()
        normalized = normalize_id_number(identification)
        job = await self.jobs.create(
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            job_type=JobType.INTERMEDIARY_CHECK,
        )
        await self.jobs.add_event(job, "EXTERNAL_REQUEST_STARTED", message="checkIntermediary")
        remote = await self.provider.check_intermediary(identification=normalized)
        await self.jobs.add_event(
            job,
            "EXTERNAL_RESPONSE_RECEIVED",
            metadata={"found": remote is not None},
        )
        local = await IntermediaryRepository(self.session, self.ctx).find_by_identification(
            normalized
        )
        await self.jobs.transition(job, JobStatus.COMPLETED)
        await self.audit.record(
            action="insurance.intermediary_check",
            resource="intermediary",
            resource_id=str(local.id) if local else None,
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            metadata={"identification": normalized, "provider_found": remote is not None},
        )
        return {
            "job_id": job.job_key,
            "identification": normalized,
            "provider": remote,
            "local": intermediary_to_public(local) if local else None,
        }

    async def ensure_intermediary(self, body: EnsureIntermediaryRequest) -> dict:
        self.ctx.require_staff_principal()
        self.ctx.require_active_tenant()
        normalized = normalize_id_number(body.identification)
        job = await self.jobs.create(
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            job_type=JobType.INTERMEDIARY_REGISTRATION,
        )
        await self.jobs.add_event(job, "EXTERNAL_REQUEST_STARTED", message="checkIntermediary")
        remote = await self.provider.check_intermediary(identification=normalized)
        await self.jobs.add_event(
            job,
            "EXTERNAL_RESPONSE_RECEIVED",
            metadata={"found": remote is not None},
        )
        if remote is None and body.create_if_missing:
            await self.jobs.add_event(
                job, "EXTERNAL_REQUEST_STARTED", message="registerIntermediary"
            )
            remote = await self.provider.register_intermediary(
                {
                    "name": body.name,
                    "email": str(body.email).lower(),
                    "phone": normalize_phone(body.phone),
                    "identification": normalized,
                    "kra_pin": normalize_kra_pin(body.kra_pin),
                }
            )
            await self.jobs.add_event(
                job, "EXTERNAL_RESPONSE_RECEIVED", message="registerIntermediary"
            )

        service = IntermediaryService(self.session, self.ctx)
        repo = IntermediaryRepository(self.session, self.ctx)
        local = await repo.find_by_identification(normalized)
        if local is None:
            local = await service.create(
                IntermediaryCreateRequest(
                    name=body.name,
                    email=body.email,
                    phone=body.phone,
                    identification=normalized,
                    kra_pin=body.kra_pin,
                )
            )
        if remote and remote.get("external_ref"):
            local.external_intermediary_ref = str(remote["external_ref"])
            await self.session.flush()

        await self.jobs.transition(job, JobStatus.COMPLETED)
        await self.audit.record(
            action="insurance.intermediary_ensure",
            resource="intermediary",
            resource_id=str(local.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            metadata={"identification": normalized},
        )
        return {
            "job_id": job.job_key,
            "provider": remote,
            "local": intermediary_to_public(local),
        }

    async def calculate_premium(self, body: PremiumCalculateRequest) -> dict:
        self.ctx.require_active_tenant()
        job = await self.jobs.create(
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            job_type=JobType.PREMIUM_CALCULATION,
        )
        await self.jobs.add_event(job, "EXTERNAL_REQUEST_STARTED", message="calculatePremium")
        # Never trust client-provided premium — always fetch from provider
        result = await self.provider.calculate_premium(
            {
                "sum_insured": body.sum_insured,
                "capacity": body.capacity,
                "tonnage": body.tonnage,
                "cover_period": body.cover_period,
                "product": body.product,
                "cover_option": body.cover_option,
                "transaction_type": body.transaction_type,
            }
        )
        await self.jobs.add_event(job, "EXTERNAL_RESPONSE_RECEIVED", message="calculatePremium")
        await self.jobs.transition(job, JobStatus.COMPLETED)
        await self.audit.record(
            action="insurance.premium_calculate",
            resource="premium",
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            metadata={"product": body.product, "gross_premium": result.get("gross_premium")},
        )
        return {"job_id": job.job_key, "premium": result}

    async def get_catalog(self) -> dict:
        """Insurer catalog for the quote wizard, served from our DB copy."""
        from app.modules.insurer_catalog import service as insurer_catalog

        self.ctx.require_active_tenant()
        return await insurer_catalog.get_catalog(self.session, self.provider)

    async def sync_reference_data(self) -> dict:
        from app.modules.products.cache import MAKES_TTL_SECONDS, PRODUCTS_TTL_SECONDS

        self.ctx.require_staff_principal()
        self.ctx.require_active_tenant()
        products, makes, reasons = await asyncio.gather(
            self.provider.get_products(),
            self.provider.get_makes(),
            self.provider.get_cancellation_reasons(),
        )
        now = datetime.now(UTC)

        product_count = await self._upsert_products(products, now)
        make_count = await self._upsert_makes(makes, now)
        reason_count = await self._upsert_reasons(reasons)

        tenant_key = str(self.ctx.tenant_id)
        catalog_key = "definite"
        await self.cache.invalidate("products", tenant_key)
        await self.cache.invalidate("makes", tenant_key)
        await self.cache.invalidate("cancel_reasons", tenant_key)
        await self.cache.invalidate("products", catalog_key)
        await self.cache.invalidate("makes", catalog_key)
        if isinstance(products, list):
            await self.cache.set_json(
                "products", catalog_key, products, PRODUCTS_TTL_SECONDS
            )
        if isinstance(makes, list):
            await self.cache.set_json("makes", catalog_key, makes, MAKES_TTL_SECONDS)

        await self.audit.record(
            action="insurance.reference_sync",
            resource="reference_data",
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            metadata={
                "products": product_count,
                "makes": make_count,
                "reasons": reason_count,
            },
        )
        from app.modules.insurer_catalog import service as insurer_catalog

        insurer_catalog.schedule_refresh(self.provider, trigger="staff", force=True)
        return {
            "products_upserted": product_count,
            "makes_upserted": make_count,
            "reasons_upserted": reason_count,
        }

    async def _upsert_products(self, products: list[dict], now: datetime) -> int:
        count = 0
        for item in products:
            code = str(item["code"]).upper()
            existing = await self.session.scalar(
                select(InsuranceProduct).where(
                    InsuranceProduct.tenant_id == self.ctx.tenant_id,
                    InsuranceProduct.code == code,
                )
            )
            if existing is None:
                existing = InsuranceProduct(
                    id=uuid4(),
                    tenant_id=self.ctx.tenant_id,
                    code=code,
                    name=item["name"],
                    description=item.get("description"),
                    cover_options=_normalize_cover_options(item.get("cover_options")),
                    is_active=True,
                    provider_code=item.get("provider_code") or "DEFINITE_ASSURANCE",
                    metadata_json={
                        "external_id": item.get("external_id"),
                        "category": item.get("category"),
                    },
                    synced_at=now,
                )
                self.session.add(existing)
            else:
                existing.name = item["name"]
                existing.description = item.get("description")
                existing.cover_options = _normalize_cover_options(item.get("cover_options"))
                existing.provider_code = item.get("provider_code") or existing.provider_code
                existing.metadata_json = {
                    **(existing.metadata_json or {}),
                    "external_id": item.get("external_id"),
                    "category": item.get("category"),
                }
                existing.synced_at = now
                existing.is_active = True
            count += 1
        await self.session.flush()
        return count

    async def _upsert_makes(self, makes: list[dict], now: datetime) -> int:
        count = 0
        for item in makes:
            code = str(item["code"]).upper()
            existing = await self.session.scalar(
                select(VehicleMake).where(
                    VehicleMake.tenant_id == self.ctx.tenant_id,
                    VehicleMake.code == code,
                )
            )
            if existing is None:
                existing = VehicleMake(
                    id=uuid4(),
                    tenant_id=self.ctx.tenant_id,
                    code=code,
                    name=item["name"],
                    sort_order=int(item.get("sort_order") or 0),
                    is_active=True,
                    provider_code=item.get("provider_code") or "DEFINITE_ASSURANCE",
                    synced_at=now,
                )
                self.session.add(existing)
            else:
                existing.name = item["name"]
                existing.sort_order = int(item.get("sort_order") or existing.sort_order)
                existing.synced_at = now
                existing.is_active = True
            count += 1
        await self.session.flush()
        return count

    async def _upsert_reasons(self, reasons: list[dict]) -> int:
        count = 0
        for item in reasons:
            code = str(item["code"]).upper()
            existing = await self.session.scalar(
                select(CancellationReason).where(
                    CancellationReason.tenant_id == self.ctx.tenant_id,
                    CancellationReason.code == code,
                )
            )
            if existing is None:
                self.session.add(
                    CancellationReason(
                        id=uuid4(),
                        tenant_id=self.ctx.tenant_id,
                        code=code,
                        label=item["label"],
                        is_active=True,
                        provider_code=item.get("provider_code") or "DEFINITE_ASSURANCE",
                    )
                )
            else:
                existing.label = item["label"]
                existing.is_active = True
            count += 1
        await self.session.flush()
        return count


def _normalize_cover_options(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            name = item.get("name") or item.get("id")
            if name:
                out.append(str(name))
        elif item is not None:
            out.append(str(item))
    return out
