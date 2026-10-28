"""DB-backed insurer quote catalog with background refresh from the provider.

Reads never wait on the insurer once a snapshot exists: they come from a short
process memo, then from our tables. The provider is re-read in the background
when the stored copy is older than ``insurer_catalog_refresh_seconds``, and rows
are only rewritten when the provider's payload actually changed.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database.base import get_session_factory
from app.core.logging import get_logger
from app.integrations.insurance.catalog_stub import group_catalog
from app.integrations.insurance.ports import InsuranceProvider
from app.modules.insurer_catalog.models import (
    InsurerCatalogCategory,
    InsurerCatalogCoverOption,
    InsurerCatalogProduct,
    InsurerCatalogSyncRun,
    InsurerCatalogSyncState,
    InsurerVehicleMake,
    InsurerVehicleModel,
)

logger = get_logger(__name__)

PROVIDER_CODE = "DEFINITE_ASSURANCE"
# pg advisory lock id — one writer per provider across all API instances.
_SYNC_LOCK_KEY = 7_391_220_504_118_001
_MEMO_MAX_SECONDS = 300
_RECENT_SUCCESS_SECONDS = 60
_FAILURE_BACKOFF_SECONDS = 300
_INSERT_CHUNK = 500
_SYNC_STATEMENT_TIMEOUT = "60s"
_SYNC_IDLE_TIMEOUT = "60s"
# How long a first-ever catalog request waits for the stored copy before going live.
_COLD_WAIT_SECONDS = 45.0


@dataclass
class CatalogSnapshot:
    products: list[dict[str, Any]] = field(default_factory=list)
    makes: list[dict[str, Any]] = field(default_factory=list)
    last_success_at: datetime | None = None
    last_attempt_at: datetime | None = None

    @property
    def complete(self) -> bool:
        return bool(self.products) and bool(self.makes)


@dataclass
class SyncOutcome:
    status: str
    products: list[dict[str, Any]] | None = None
    makes: list[dict[str, Any]] | None = None
    products_changed: bool = False
    makes_changed: bool = False
    error: str | None = None


# ---------------------------------------------------------------- normalizing


def _clean(value: Any, limit: int) -> str:
    return str(value if value is not None else "").strip()[:limit]


def _normalize_products(items: Any) -> list[dict[str, Any]]:
    """Public product shape, identical to what the quote wizard already consumes."""
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        external_id = _clean(item.get("external_id") or item.get("code"), 64)
        name = _clean(item.get("name"), 255)
        if not external_id or not name or external_id in seen:
            continue
        seen.add(external_id)
        covers: list[dict[str, str]] = []
        cover_seen: set[str] = set()
        for cover in item.get("cover_options") or []:
            if not isinstance(cover, dict):
                continue
            cid = _clean(cover.get("id"), 64)
            cname = _clean(cover.get("name") or cid, 255)
            if not cid or cid in cover_seen:
                continue
            cover_seen.add(cid)
            covers.append({"id": cid, "name": cname})
        description = item.get("description")
        out.append(
            {
                "external_id": external_id,
                "code": _clean(item.get("code") or external_id, 64).upper(),
                "name": name,
                "description": str(description) if description is not None else None,
                "category": _clean(item.get("category"), 128) or None,
                "cover_options": covers,
                "provider_code": _clean(item.get("provider_code") or PROVIDER_CODE, 64),
            }
        )
    return out


def _normalize_makes(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        external_id = _clean(item.get("external_id") or item.get("code"), 64)
        name = _clean(item.get("name"), 128)
        if not external_id or not name or external_id in seen:
            continue
        seen.add(external_id)
        models: list[dict[str, str]] = []
        model_seen: set[str] = set()
        for model in item.get("models") or []:
            if not isinstance(model, dict):
                continue
            mid = _clean(model.get("id"), 64)
            mname = _clean(model.get("name") or mid, 128)
            if not mid or mid in model_seen:
                continue
            model_seen.add(mid)
            models.append({"id": mid, "name": mname})
        out.append(
            {
                "external_id": external_id,
                "code": _clean(item.get("code") or external_id, 64),
                "name": name,
                "sort_order": (len(out) + 1) * 10,
                "models": models,
                "provider_code": _clean(item.get("provider_code") or PROVIDER_CODE, 64),
            }
        )
    return out


def content_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def catalog_source(provider: InsuranceProvider) -> InsuranceProvider:
    """Talk to the real insurer so a transient failure never stores stub data."""
    from app.integrations.insurance.factory import ResilientInsuranceProvider
    from app.modules.guest.insurance_gateway import GuestInsuranceGateway

    inner = provider
    if isinstance(inner, GuestInsuranceGateway):
        inner = inner._inner  # noqa: SLF001
    if isinstance(inner, ResilientInsuranceProvider):
        inner = inner.primary
    return inner


# --------------------------------------------------------------------- reads


async def load_snapshot(session: AsyncSession) -> CatalogSnapshot:
    state = await session.scalar(
        select(InsurerCatalogSyncState).where(
            InsurerCatalogSyncState.provider_code == PROVIDER_CODE
        )
    )
    product_rows = (
        await session.execute(
            select(
                InsurerCatalogProduct.id,
                InsurerCatalogProduct.external_id,
                InsurerCatalogProduct.code,
                InsurerCatalogProduct.name,
                InsurerCatalogProduct.description,
                InsurerCatalogProduct.category,
                InsurerCatalogProduct.provider_code,
            )
            .where(
                InsurerCatalogProduct.provider_code == PROVIDER_CODE,
                InsurerCatalogProduct.is_active.is_(True),
            )
            .order_by(InsurerCatalogProduct.sort_order, InsurerCatalogProduct.external_id)
        )
    ).all()
    cover_rows = (
        await session.execute(
            select(
                InsurerCatalogCoverOption.product_id,
                InsurerCatalogCoverOption.external_id,
                InsurerCatalogCoverOption.name,
            )
            .join(
                InsurerCatalogProduct,
                InsurerCatalogProduct.id == InsurerCatalogCoverOption.product_id,
            )
            .where(
                InsurerCatalogProduct.provider_code == PROVIDER_CODE,
                InsurerCatalogProduct.is_active.is_(True),
                InsurerCatalogCoverOption.is_active.is_(True),
            )
            .order_by(InsurerCatalogCoverOption.product_id, InsurerCatalogCoverOption.sort_order)
        )
    ).all()
    covers_by_product: dict[Any, list[dict[str, str]]] = {}
    for row in cover_rows:
        covers_by_product.setdefault(row.product_id, []).append(
            {"id": row.external_id, "name": row.name}
        )
    products = [
        {
            "external_id": row.external_id,
            "code": row.code,
            "name": row.name,
            "description": row.description,
            "category": row.category,
            "cover_options": covers_by_product.get(row.id, []),
            "provider_code": row.provider_code,
        }
        for row in product_rows
    ]

    make_rows = (
        await session.execute(
            select(
                InsurerVehicleMake.id,
                InsurerVehicleMake.external_id,
                InsurerVehicleMake.code,
                InsurerVehicleMake.name,
                InsurerVehicleMake.sort_order,
                InsurerVehicleMake.provider_code,
            )
            .where(
                InsurerVehicleMake.provider_code == PROVIDER_CODE,
                InsurerVehicleMake.is_active.is_(True),
            )
            .order_by(InsurerVehicleMake.sort_order, InsurerVehicleMake.name)
        )
    ).all()
    model_rows = (
        await session.execute(
            select(
                InsurerVehicleModel.make_id,
                InsurerVehicleModel.external_id,
                InsurerVehicleModel.name,
            )
            .join(InsurerVehicleMake, InsurerVehicleMake.id == InsurerVehicleModel.make_id)
            .where(
                InsurerVehicleMake.provider_code == PROVIDER_CODE,
                InsurerVehicleMake.is_active.is_(True),
                InsurerVehicleModel.is_active.is_(True),
            )
            .order_by(InsurerVehicleModel.make_id, InsurerVehicleModel.sort_order)
        )
    ).all()
    models_by_make: dict[Any, list[dict[str, str]]] = {}
    for row in model_rows:
        models_by_make.setdefault(row.make_id, []).append(
            {"id": row.external_id, "name": row.name}
        )
    makes = [
        {
            "external_id": row.external_id,
            "code": row.code,
            "name": row.name,
            "sort_order": row.sort_order,
            "models": models_by_make.get(row.id, []),
            "provider_code": row.provider_code,
        }
        for row in make_rows
    ]
    return CatalogSnapshot(
        products=products,
        makes=makes,
        last_success_at=state.last_success_at if state else None,
        last_attempt_at=state.last_attempt_at if state else None,
    )


def is_stale(snapshot: CatalogSnapshot, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    if snapshot.last_success_at is None:
        return True
    refresh = timedelta(seconds=max(60, get_settings().insurer_catalog_refresh_seconds))
    if now - snapshot.last_success_at < refresh:
        return False
    # Provider down: do not hammer it from every request.
    if snapshot.last_attempt_at and now - snapshot.last_attempt_at < timedelta(
        seconds=_FAILURE_BACKOFF_SECONDS
    ):
        return False
    return True


_memo: tuple[float, CatalogSnapshot] | None = None


def _memo_seconds() -> int:
    return max(10, min(_MEMO_MAX_SECONDS, get_settings().insurer_catalog_refresh_seconds))


def remember(snapshot: CatalogSnapshot) -> None:
    global _memo
    _memo = (time.monotonic() + _memo_seconds(), snapshot)


def recall() -> CatalogSnapshot | None:
    hit = _memo
    if hit is None or time.monotonic() >= hit[0]:
        return None
    return hit[1]


def forget() -> None:
    global _memo
    _memo = None


def catalog_payload(snapshot: CatalogSnapshot, source: str) -> dict[str, Any]:
    return {
        "categories": group_catalog(snapshot.products),
        "products": snapshot.products,
        "makes": snapshot.makes,
        "source": source,
    }


# -------------------------------------------------------------------- writes


def _chunks(rows: list[dict[str, Any]], size: int = _INSERT_CHUNK):
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


async def _apply_products(
    session: AsyncSession, products: list[dict[str, Any]], now: datetime
) -> None:
    groups = group_catalog(products)
    category_ids: dict[str, Any] = {}
    effective: dict[str, str] = {}
    category_rows = []
    for idx, group in enumerate(groups):
        category_rows.append(
            {
                "id": uuid4(),
                "provider_code": PROVIDER_CODE,
                "name": group["category"][:128],
                "sort_order": (idx + 1) * 10,
                "product_count": int(group["product_count"]),
                "is_active": True,
            }
        )
        for product in group["products"]:
            effective[product["external_id"]] = group["category"][:128]
    if category_rows:
        stmt = pg_insert(InsurerCatalogCategory).values(category_rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_insurer_catalog_categories_provider_name",
            set_={
                "sort_order": stmt.excluded.sort_order,
                "product_count": stmt.excluded.product_count,
                "is_active": True,
                "updated_at": now,
            },
        ).returning(InsurerCatalogCategory.id, InsurerCatalogCategory.name)
        for row in (await session.execute(stmt)).all():
            category_ids[row.name] = row.id
    await session.execute(
        update(InsurerCatalogCategory)
        .where(
            InsurerCatalogCategory.provider_code == PROVIDER_CODE,
            InsurerCatalogCategory.name.not_in(list(category_ids) or [""]),
        )
        .values(is_active=False, product_count=0, updated_at=now)
        .execution_options(synchronize_session=False)
    )

    product_rows = [
        {
            "id": uuid4(),
            "provider_code": PROVIDER_CODE,
            "external_id": item["external_id"],
            "code": item["code"],
            "name": item["name"],
            "description": item["description"],
            "category": item["category"],
            "category_id": category_ids.get(effective.get(item["external_id"], "")),
            "sort_order": idx,
            "is_active": True,
            "content_hash": content_hash(item),
            "raw": item,
            "first_seen_at": now,
            "last_seen_at": now,
        }
        for idx, item in enumerate(products)
    ]
    product_ids: dict[str, Any] = {}
    for chunk in _chunks(product_rows):
        stmt = pg_insert(InsurerCatalogProduct).values(chunk)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_insurer_catalog_products_provider_external",
            set_={
                "code": stmt.excluded.code,
                "name": stmt.excluded.name,
                "description": stmt.excluded.description,
                "category": stmt.excluded.category,
                "category_id": stmt.excluded.category_id,
                "sort_order": stmt.excluded.sort_order,
                "is_active": True,
                "content_hash": stmt.excluded.content_hash,
                "raw": stmt.excluded.raw,
                "last_seen_at": now,
                "updated_at": now,
            },
        ).returning(InsurerCatalogProduct.id, InsurerCatalogProduct.external_id)
        for row in (await session.execute(stmt)).all():
            product_ids[row.external_id] = row.id
    await session.execute(
        update(InsurerCatalogProduct)
        .where(
            InsurerCatalogProduct.provider_code == PROVIDER_CODE,
            InsurerCatalogProduct.external_id.not_in(list(product_ids) or [""]),
        )
        .values(is_active=False, updated_at=now)
        .execution_options(synchronize_session=False)
    )

    cover_rows = []
    for item in products:
        product_id = product_ids[item["external_id"]]
        for idx, cover in enumerate(item["cover_options"]):
            cover_rows.append(
                {
                    "id": uuid4(),
                    "product_id": product_id,
                    "external_id": cover["id"],
                    "name": cover["name"],
                    "sort_order": idx,
                    "is_active": True,
                    "updated_at": now,
                }
            )
    for chunk in _chunks(cover_rows):
        stmt = pg_insert(InsurerCatalogCoverOption).values(chunk)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_insurer_catalog_cover_options_product_external",
            set_={
                "name": stmt.excluded.name,
                "sort_order": stmt.excluded.sort_order,
                "is_active": True,
                "updated_at": now,
            },
        )
        await session.execute(stmt)
    # Every current cover option was stamped with ``now`` above; anything older is gone.
    await session.execute(
        update(InsurerCatalogCoverOption)
        .where(
            InsurerCatalogCoverOption.product_id.in_(
                select(InsurerCatalogProduct.id).where(
                    InsurerCatalogProduct.provider_code == PROVIDER_CODE
                )
            ),
            InsurerCatalogCoverOption.is_active.is_(True),
            InsurerCatalogCoverOption.updated_at < now,
        )
        .values(is_active=False, updated_at=now)
        .execution_options(synchronize_session=False)
    )


async def _apply_makes(session: AsyncSession, makes: list[dict[str, Any]], now: datetime) -> None:
    make_rows = [
        {
            "id": uuid4(),
            "provider_code": PROVIDER_CODE,
            "external_id": item["external_id"],
            "code": item["code"],
            "name": item["name"],
            "sort_order": item["sort_order"],
            "is_active": True,
            "content_hash": content_hash(item),
            "first_seen_at": now,
            "last_seen_at": now,
        }
        for item in makes
    ]
    make_ids: dict[str, Any] = {}
    for chunk in _chunks(make_rows):
        stmt = pg_insert(InsurerVehicleMake).values(chunk)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_insurer_vehicle_makes_provider_external",
            set_={
                "code": stmt.excluded.code,
                "name": stmt.excluded.name,
                "sort_order": stmt.excluded.sort_order,
                "is_active": True,
                "content_hash": stmt.excluded.content_hash,
                "last_seen_at": now,
                "updated_at": now,
            },
        ).returning(InsurerVehicleMake.id, InsurerVehicleMake.external_id)
        for row in (await session.execute(stmt)).all():
            make_ids[row.external_id] = row.id
    await session.execute(
        update(InsurerVehicleMake)
        .where(
            InsurerVehicleMake.provider_code == PROVIDER_CODE,
            InsurerVehicleMake.is_active.is_(True),
            InsurerVehicleMake.last_seen_at < now,
        )
        .values(is_active=False, updated_at=now)
        .execution_options(synchronize_session=False)
    )

    model_rows = []
    for item in makes:
        make_id = make_ids[item["external_id"]]
        for idx, model in enumerate(item["models"]):
            model_rows.append(
                {
                    "id": uuid4(),
                    "make_id": make_id,
                    "external_id": model["id"],
                    "name": model["name"],
                    "sort_order": idx,
                    "is_active": True,
                    "updated_at": now,
                }
            )
    for chunk in _chunks(model_rows):
        stmt = pg_insert(InsurerVehicleModel).values(chunk)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_insurer_vehicle_models_make_external",
            set_={
                "name": stmt.excluded.name,
                "sort_order": stmt.excluded.sort_order,
                "is_active": True,
                "updated_at": now,
            },
        )
        await session.execute(stmt)
    # Every current model was stamped with ``now`` above; anything older is gone.
    await session.execute(
        update(InsurerVehicleModel)
        .where(
            InsurerVehicleModel.make_id.in_(
                select(InsurerVehicleMake.id).where(
                    InsurerVehicleMake.provider_code == PROVIDER_CODE
                )
            ),
            InsurerVehicleModel.is_active.is_(True),
            InsurerVehicleModel.updated_at < now,
        )
        .values(is_active=False, updated_at=now)
        .execution_options(synchronize_session=False)
    )


def _error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:500]


async def _record_failure(trigger: str, error: str, started: datetime, t0: float) -> None:
    now = datetime.now(UTC)
    async with get_session_factory()() as session:
        state = await session.get(InsurerCatalogSyncState, PROVIDER_CODE)
        if state is None:
            state = InsurerCatalogSyncState(provider_code=PROVIDER_CODE)
            session.add(state)
        state.last_attempt_at = now
        state.last_error = error
        state.consecutive_failures = int(state.consecutive_failures or 0) + 1
        session.add(
            InsurerCatalogSyncRun(
                provider_code=PROVIDER_CODE,
                trigger=trigger,
                status="FAILED",
                error=error,
                duration_ms=int((time.monotonic() - t0) * 1000),
                started_at=started,
                finished_at=now,
            )
        )
        await session.commit()


async def sync_catalog(
    provider: InsuranceProvider, *, trigger: str, force: bool = False
) -> SyncOutcome:
    """Fetch products + makes from the insurer and store whatever changed."""
    started = datetime.now(UTC)
    t0 = time.monotonic()
    source = catalog_source(provider)
    fetched = await asyncio.gather(
        source.get_products(), source.get_makes(), return_exceptions=True
    )
    errors: list[str] = []
    products = makes = None
    if isinstance(fetched[0], BaseException):
        errors.append(f"products: {_error_text(fetched[0])}")
    else:
        products = _normalize_products(fetched[0]) or None
        if products is None:
            errors.append("products: provider returned an empty catalog")
    if isinstance(fetched[1], BaseException):
        errors.append(f"makes: {_error_text(fetched[1])}")
    else:
        makes = _normalize_makes(fetched[1]) or None
        if makes is None:
            errors.append("makes: provider returned an empty list")
    error = "; ".join(errors) or None

    if products is None and makes is None:
        logger.warning("insurer_catalog_sync_failed", extra={"trigger": trigger, "error": error})
        try:
            await _record_failure(trigger, error or "no data", started, t0)
        except Exception:
            logger.exception("insurer_catalog_sync_failure_not_recorded")
        return SyncOutcome(status="failed", error=error)

    async with get_session_factory()() as session:
        locked = await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": _SYNC_LOCK_KEY}
        )
        if not locked:
            await session.rollback()
            return SyncOutcome(status="skipped", products=products, makes=makes, error=error)
        # A stalled writer must not keep the advisory lock (and row locks) indefinitely.
        await session.execute(text(f"SET LOCAL statement_timeout = '{_SYNC_STATEMENT_TIMEOUT}'"))
        await session.execute(
            text(f"SET LOCAL idle_in_transaction_session_timeout = '{_SYNC_IDLE_TIMEOUT}'")
        )

        now = datetime.now(UTC)
        state = await session.get(InsurerCatalogSyncState, PROVIDER_CODE)
        if state is None:
            state = InsurerCatalogSyncState(provider_code=PROVIDER_CODE)
            session.add(state)
        elif (
            not force
            and state.last_success_at is not None
            and now - state.last_success_at < timedelta(seconds=_RECENT_SUCCESS_SECONDS)
            and trigger != "cold"
        ):
            await session.rollback()
            return SyncOutcome(status="skipped", products=products, makes=makes, error=error)

        products_changed = makes_changed = False
        if products is not None:
            digest = content_hash(products)
            if force or digest != state.products_hash:
                await _apply_products(session, products, now)
                state.products_hash = digest
                products_changed = True
            state.product_count = len(products)
        if makes is not None:
            digest = content_hash(makes)
            if force or digest != state.makes_hash:
                await _apply_makes(session, makes, now)
                state.makes_hash = digest
                makes_changed = True
            state.make_count = len(makes)
            state.model_count = sum(len(item["models"]) for item in makes)

        changed = products_changed or makes_changed
        status = "partial" if error else ("changed" if changed else "unchanged")
        state.last_attempt_at = now
        if error:
            state.last_error = error
            state.consecutive_failures = int(state.consecutive_failures or 0) + 1
        else:
            state.last_success_at = now
            state.last_error = None
            state.consecutive_failures = 0
        if products_changed or makes_changed:
            state.last_changed_at = now
        session.add(
            InsurerCatalogSyncRun(
                provider_code=PROVIDER_CODE,
                trigger=trigger,
                status=status.upper(),
                products_changed=products_changed,
                makes_changed=makes_changed,
                product_count=state.product_count,
                make_count=state.make_count,
                model_count=state.model_count,
                duration_ms=int((time.monotonic() - t0) * 1000),
                error=error,
                started_at=started,
                finished_at=now,
            )
        )
        await session.commit()

    if products_changed or makes_changed:
        forget()
    logger.info(
        "insurer_catalog_synced",
        extra={
            "trigger": trigger,
            "status": status,
            "products_changed": products_changed,
            "makes_changed": makes_changed,
        },
    )
    return SyncOutcome(
        status=status,
        products=products,
        makes=makes,
        products_changed=products_changed,
        makes_changed=makes_changed,
        error=error,
    )


# ------------------------------------------------------------- orchestration

_refresh_task: asyncio.Task[SyncOutcome] | None = None


def schedule_refresh(
    provider: InsuranceProvider | None = None, *, trigger: str = "stale", force: bool = False
) -> asyncio.Task[SyncOutcome]:
    """Start (or join) the single in-process refresh."""
    global _refresh_task
    loop = asyncio.get_running_loop()
    task = _refresh_task
    if task is not None and not task.done() and task.get_loop() is loop:
        return task
    if provider is None:
        from app.integrations.insurance.factory import get_insurance_provider

        provider = get_insurance_provider()

    async def _run() -> SyncOutcome:
        try:
            return await sync_catalog(provider, trigger=trigger, force=force)
        except Exception as exc:
            logger.exception("insurer_catalog_refresh_crashed", extra={"trigger": trigger})
            return SyncOutcome(status="failed", error=_error_text(exc))

    _refresh_task = loop.create_task(_run(), name=f"insurer-catalog-{trigger}")
    return _refresh_task


async def get_catalog(session: AsyncSession, provider: InsuranceProvider) -> dict[str, Any]:
    """Catalog for the quote wizard — from us, refreshed from the insurer in the background."""
    snapshot = recall()
    if snapshot is not None:
        return catalog_payload(snapshot, "memory")

    snapshot = await load_snapshot(session)
    if snapshot.complete:
        remember(snapshot)
        if get_settings().insurer_catalog_background_refresh and is_stale(snapshot):
            schedule_refresh(provider, trigger="stale")
        return catalog_payload(snapshot, "database")

    # First run (or a half-filled store): wait once for the insurer, then serve from us.
    try:
        outcome = await asyncio.wait_for(
            asyncio.shield(schedule_refresh(provider, trigger="cold")),
            timeout=_COLD_WAIT_SECONDS,
        )
    except TimeoutError:
        logger.warning("insurer_catalog_cold_wait_timeout")
        outcome = SyncOutcome(status="pending")
    products = snapshot.products or (outcome.products or [])
    makes = snapshot.makes or (outcome.makes or [])
    if products and makes:
        fresh = CatalogSnapshot(
            products=products, makes=makes, last_success_at=datetime.now(UTC)
        )
        remember(fresh)
        return catalog_payload(fresh, "provider")

    # Insurer unreachable and nothing stored: previous live behaviour (stub in dev,
    # error in production). Not remembered, so the next request tries us again.
    if not products:
        products = _normalize_products(await provider.get_products())
    if not makes:
        makes = _normalize_makes(await provider.get_makes())
    return catalog_payload(CatalogSnapshot(products=products, makes=makes), "provider")


# ----------------------------------------------------------- background loop


class CatalogRefresher:
    """Keeps the stored catalog fresh while the API is running."""

    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="insurer-catalog-refresher")

    async def stop(self) -> None:
        self._stop.set()
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    async def _sleep(self, seconds: float) -> bool:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
            return True
        except TimeoutError:
            return False

    async def _tick(self) -> None:
        async with get_session_factory()() as session:
            state = await session.get(InsurerCatalogSyncState, PROVIDER_CODE)
            snapshot = CatalogSnapshot(
                last_success_at=state.last_success_at if state else None,
                last_attempt_at=state.last_attempt_at if state else None,
            )
        if is_stale(snapshot):
            await schedule_refresh(trigger="scheduled")

    async def _run(self) -> None:
        interval = max(60, get_settings().insurer_catalog_refresh_seconds)
        # Let the API finish booting before the first insurer call.
        if await self._sleep(5 + random.uniform(0, 10)):  # noqa: S311
            return
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception:
                logger.exception("insurer_catalog_refresher_tick_failed")
            jitter = random.uniform(0, min(120, interval * 0.1))  # noqa: S311
            if await self._sleep(min(interval / 2, 600) + jitter):
                return


_REFRESHER: CatalogRefresher | None = None


async def start_catalog_refresher() -> CatalogRefresher | None:
    global _REFRESHER
    if not get_settings().insurer_catalog_background_refresh:
        return None
    if _REFRESHER is None:
        _REFRESHER = CatalogRefresher()
    _REFRESHER.start()
    return _REFRESHER


async def stop_catalog_refresher() -> None:
    global _REFRESHER
    refresher = _REFRESHER
    _REFRESHER = None
    if refresher is not None:
        await refresher.stop()
