"""Reference data admin — countries (DB catalog)."""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db, require_permissions
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationAppError
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.modules.audit.service import AuditService
from app.modules.reference.models import Country, Currency

router = APIRouter(prefix="/reference", tags=["Reference"])


class CountryCreateRequest(BaseModel):
    iso2: str = Field(min_length=2, max_length=2)
    iso3: str | None = Field(default=None, min_length=3, max_length=3)
    name: str = Field(min_length=2, max_length=128)
    phone_code: str | None = Field(default=None, max_length=8)
    currency_code: str | None = Field(default=None, max_length=8)
    status: str = Field(default="ACTIVE", pattern="^(ACTIVE|DISABLED)$")

    model_config = {"extra": "forbid"}


class CountryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)
    phone_code: str | None = Field(default=None, max_length=8)
    currency_code: str | None = Field(default=None, max_length=8)
    iso3: str | None = Field(default=None, min_length=3, max_length=3)
    status: str | None = Field(default=None, pattern="^(ACTIVE|DISABLED)$")

    model_config = {"extra": "forbid"}


def _country_public(row: Country) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "iso2": row.iso2,
        "iso3": row.iso3,
        "name": row.name,
        "phone_code": row.phone_code,
        "currency_code": row.currency_code,
        "status": row.status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _phone_dial(phone_code: str | None) -> str | None:
    """Normalize DB phone_code (+254) → dial digits (254)."""
    if not phone_code:
        return None
    digits = "".join(ch for ch in str(phone_code) if ch.isdigit())
    return digits or None


@router.get("/phone-countries")
async def list_phone_countries(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Public catalog of ACTIVE countries with dial codes for phone inputs."""
    rows = (
        await db.scalars(
            select(Country)
            .where(
                Country.deleted_at.is_(None),
                Country.status == "ACTIVE",
                Country.phone_code.is_not(None),
            )
            .order_by(Country.name.asc())
        )
    ).all()
    items: list[dict[str, str]] = []
    for row in rows:
        dial = _phone_dial(row.phone_code)
        if not dial:
            continue
        items.append(
            {
                "iso": row.iso2.upper(),
                "name": row.name,
                "dial": dial,
            }
        )
    default_iso = next((row["iso"] for row in items if row["iso"] == "KE"), None)
    if default_iso is None and items:
        default_iso = items[0]["iso"]
    return success_response(
        {"items": items, "default_iso": default_iso, "total": len(items)},
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/countries")
async def list_countries(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext,
        Depends(require_permissions("platform:config:manage", "platform:tenant:manage", "tenant:manage")),
    ],
) -> dict:
    rows = (
        await db.scalars(
            select(Country)
            .where(Country.deleted_at.is_(None))
            .order_by(Country.name)
        )
    ).all()
    items = [_country_public(r) for r in rows]
    return success_response(
        {"items": items, "total": len(items)},
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/currencies")
async def list_currencies(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext,
        Depends(require_permissions("platform:config:manage", "platform:tenant:manage", "tenant:manage")),
    ],
) -> dict:
    rows = (
        await db.scalars(
            select(Currency).where(Currency.deleted_at.is_(None)).order_by(Currency.code)
        )
    ).all()
    items = [
        {
            "code": r.code,
            "name": r.name,
            "symbol": r.symbol,
            "decimal_places": r.decimal_places,
            "status": r.status,
        }
        for r in rows
    ]
    return success_response(
        {"items": items, "total": len(items)},
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/countries")
async def create_country(
    body: CountryCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext,
        Depends(require_permissions("platform:config:manage", "platform:tenant:manage")),
    ],
) -> dict:
    iso2 = body.iso2.upper().strip()
    existing = await db.scalar(select(Country).where(Country.iso2 == iso2))
    if existing and existing.deleted_at is None:
        raise ConflictError(f"Country {iso2} already exists")
    if body.currency_code:
        currency = await db.get(Currency, body.currency_code.upper())
        if currency is None or currency.deleted_at is not None:
            raise ValidationAppError("Unknown currency_code")
    country = Country(
        iso2=iso2,
        iso3=body.iso3.upper() if body.iso3 else None,
        name=body.name.strip(),
        phone_code=body.phone_code,
        currency_code=body.currency_code.upper() if body.currency_code else None,
        status=body.status,
    )
    db.add(country)
    await db.flush()
    await AuditService(db).record(
        action="reference.country_create",
        resource="country",
        resource_id=str(country.id),
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        metadata={"iso2": country.iso2, "status": country.status},
    )
    await db.commit()
    await db.refresh(country)
    return success_response(
        _country_public(country),
        message="Country created",
        request_id=getattr(request.state, "request_id", None),
    )


@router.patch("/countries/{country_id}")
async def update_country(
    country_id: UUID,
    body: CountryUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext,
        Depends(require_permissions("platform:config:manage", "platform:tenant:manage")),
    ],
) -> dict:
    country = await db.get(Country, country_id)
    if country is None or country.deleted_at is not None:
        raise ResourceNotFoundError("Country not found")
    if body.name is not None:
        country.name = body.name.strip()
    if body.phone_code is not None:
        country.phone_code = body.phone_code
    if body.iso3 is not None:
        country.iso3 = body.iso3.upper()
    if body.currency_code is not None:
        code = body.currency_code.upper()
        currency = await db.get(Currency, code)
        if currency is None or currency.deleted_at is not None:
            raise ValidationAppError("Unknown currency_code")
        country.currency_code = code
    if body.status is not None:
        country.status = body.status
    country.updated_at = datetime.now(UTC)
    await AuditService(db).record(
        action="reference.country_update",
        resource="country",
        resource_id=str(country.id),
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        metadata={"iso2": country.iso2, "status": country.status},
    )
    await db.commit()
    await db.refresh(country)
    return success_response(
        _country_public(country),
        message="Country updated",
        request_id=getattr(request.state, "request_id", None),
    )
