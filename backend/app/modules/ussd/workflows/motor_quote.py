"""MOTOR_QUOTE — website-aligned guest cover flow over USSD.

Order (same idea as QuoteWizard Product → Client → Vehicle → Pay):
  category → product → cover option → period → make → model →
  ID → full name → email → registration → chassis → confirm → M-Pesa pay

Catalog reads prefer our insurer_catalog DB snapshot (fast). Lists use
``99 More`` for pagination. Full name is one step; backend splits first/last.
Phone always comes from the dialing MSISDN. ``0`` / ``00`` are handled by the
session engine (back / main menu).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import StarServeError, ValidationAppError
from app.core.validation import normalize_phone
from app.integrations.insurance.factory import get_insurance_provider
from app.modules.guest.service import GuestService
from app.modules.insurance.issuance_schemas import (
    IssuanceClientRequest,
    IssuancePayRequest,
    IssuanceSubmitRequest,
)
from app.modules.insurance.fees import monthly_referral_cost
from app.modules.insurance.schemas import PremiumCalculateRequest
from app.modules.insurer_catalog import service as insurer_catalog
from app.modules.ussd.channel import prepare_ussd_request, ussd_guest_context
from app.modules.ussd.enums import (
    UssdEventType,
    UssdOutcomeCategory,
    UssdResponseType,
    UssdWorkflowAction,
)
from app.modules.ussd.models import UssdSession
from app.modules.ussd.privacy import normalize_msisdn
from app.modules.ussd.workflows.base import WorkflowResult

_COVER_PERIODS = (
    ("1", "Monthly"),
    ("2", "Annually"),
)
_DEFAULT_CAPACITY = Decimal("4")
_MAX_PAGE = 9
_MORE_KEY = "99"
# Engine truncates past this; list screens must fit so items are not cut off.
_USSD_MAX_CHARS = 160
# Single spaces — every character counts toward the ~160 USSD screen limit.
_NAV_FOOTER = "0 Back 00 Main menu"


def _nav(msg: str) -> str:
    return f"{msg}\n{_NAV_FOOTER}"


def split_full_name(raw: str) -> tuple[str, str]:
    parts = [p for p in (raw or "").strip().split() if p]
    if len(parts) < 2:
        raise ValidationAppError("Enter full name (first and last)")
    return parts[0][:128], " ".join(parts[1:])[:128]


def _clip_label(raw: str, length: int) -> str:
    """Hard-trim a stored Definite/DB label to fit USSD — never invent a new name."""
    text = " ".join((raw or "").split()) or "Option"
    if length < 1:
        return text[:1]
    if len(text) <= length:
        return text
    return text[:length].rstrip()


def _fit_menu_page(
    title: str,
    items: list[Any],
    offset: int,
    *,
    label_fn,
    max_chars: int = _USSD_MAX_CHARS,
) -> tuple[list[Any], str, bool]:
    """Pack up to 9 options that fit the USSD character budget.

    Prefers a full page of 9 shorter labels over fewer long ones so the
    engine never truncates mid-list. Pagination uses an absolute ``offset``.
    """
    offset = max(0, int(offset or 0))
    remaining = items[offset:]

    def _compose(lines: list[str], *, more: bool) -> str:
        body = "\n".join([title, *lines] + ([f"{_MORE_KEY} More"] if more else []))
        return _nav(body)

    def _lines_for(count: int, length: int) -> list[str]:
        out: list[str] = []
        for i in range(count):
            raw = str(label_fn(remaining[i]) or "Option").strip() or "Option"
            out.append(f"{i + 1}. {_clip_label(raw, length)}")
        return out

    max_count = min(_MAX_PAGE, len(remaining))
    # Pick the best fit: keep enough of the stored Definite name for cover
    # text (length >= 18 preferred), then maximize how many options we show.
    best: tuple[tuple[int, int, int], int, str, bool] | None = None
    for count in range(max_count, 0, -1):
        has_more = offset + count < len(items)
        for length in (28, 24, 22, 20, 18, 16, 14, 12, 10, 8):
            lines = _lines_for(count, length)
            message = _compose(lines, more=has_more)
            if len(message) > max_chars:
                continue
            score = (1 if length >= 18 else 0, count, length)
            if best is None or score > best[0]:
                best = (score, count, message, has_more)
    if best is not None:
        _, count, message, has_more = best
        return remaining[:count], message, has_more

    if remaining:
        raw = str(label_fn(remaining[0]) or "Option").strip() or "Option"
        lines = [f"1. {_clip_label(raw, 8)}"]
        has_more = len(remaining) > 1
        return remaining[:1], _compose(lines, more=has_more), has_more
    return [], _compose([], more=False), False


def _resolve_shown_choice(
    items: list[Any], offset: int, shown: int, choice: str
) -> Any | None:
    raw = (choice or "").strip()
    # Defensive: accept "1." / trailing junk from some handsets; ignore * trails
    # (Birdview cumulative INPUT is normalized in the adapter first).
    if "*" in raw:
        raw = raw.split("*")[-1].strip()
    match = re.match(r"^(\d+)", raw)
    if not match:
        return None
    idx = int(match.group(1))
    if idx < 1 or idx > min(shown, _MAX_PAGE):
        return None
    absolute = offset + idx - 1
    if absolute < 0 or absolute >= len(items):
        return None
    return items[absolute]


def _format_product_label(name: str) -> str:
    """Match QuoteWizard ``formatProductLabel`` — class name before `` - ``."""
    spaced = " ".join((name or "").split())
    if not spaced:
        return "Product"
    head = spaced.split(" - ", 1)[0].split(" — ", 1)[0].strip() or spaced
    titled = head.title()
    for token in ("Tpo", "Psv", "Ira"):
        titled = titled.replace(token, token.upper())
    return titled.replace("Chauffer", "Chauffeur")


def _product_label(item: Any) -> str:
    return _format_product_label(str(item.get("name") or item.get("code") or "Product"))


def _category_label(item: Any) -> str:
    return str(item.get("category") or item.get("name") or "Class")


def _cover_label(item: Any) -> str:
    return str(item.get("name") or item.get("id") or "Cover")


_COVER_KEY_MONTHLY = re.compile(r"\s+MONTHLY$", re.IGNORECASE)


def _cover_key(name: str) -> str:
    return " ".join((name or "").strip().upper().split())


def _visible_cover_options(covers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Same filter as QuoteWizard — hide sibling MONTHLY rows when a base cover exists."""
    if not covers:
        return covers
    names = {_cover_key(str(c.get("name") or "")) for c in covers}
    visible: list[dict[str, Any]] = []
    for cover in covers:
        key = _cover_key(str(cover.get("name") or ""))
        if not _COVER_KEY_MONTHLY.search(key):
            visible.append(cover)
            continue
        base = _COVER_KEY_MONTHLY.sub("", key).strip()
        if base not in names:
            visible.append(cover)
    return visible or covers


def _priced_cover_option(
    covers: list[dict[str, Any]], selected_id: str, period: str
) -> dict[str, Any]:
    """Definite prices monthly cover via a sibling ``{Cover} MONTHLY`` option."""
    selected = next(
        (c for c in covers if str(c.get("id") or "") == str(selected_id)),
        None,
    )
    if selected is None:
        return {"id": selected_id, "name": "Cover"}
    if period != "Monthly":
        return selected
    monthly_key = f"{_cover_key(str(selected.get('name') or ''))} MONTHLY"
    for cover in covers:
        if _cover_key(str(cover.get("name") or "")) == monthly_key:
            return cover
    return selected


def _cover_display_name(name: str) -> str:
    key = _cover_key(name)
    return _COVER_KEY_MONTHLY.sub("", key).strip() or name.strip()


def _make_label(item: Any) -> str:
    return str(item.get("name") or item.get("code") or "Make")


def _model_label(item: Any) -> str:
    return str(item.get("name") or item.get("id") or "Model")


def _answers_patch(answers: dict[str, Any], **fields: Any) -> dict[str, Any]:
    """Only persist workflow fields — never the full catalog."""
    patch = dict(answers)
    patch.update(fields)
    for key in (
        "catalog_products",
        "catalog_makes",
        "catalog_models",
        "cover_options",
        "model_ids",
    ):
        patch.pop(key, None)
    return patch


class MotorQuoteWorkflow:
    action = UssdWorkflowAction.MOTOR_QUOTE.value

    def _priced_cover(self, answers: dict[str, Any]) -> dict[str, Any]:
        covers = list(answers.get("cover_option_ids") or [])
        product = answers.get("product") or {}
        selected_id = str(
            product.get("cover_option_selected_id")
            or product.get("cover_option_id")
            or ""
        )
        period = str(answers.get("cover_period") or "Monthly")
        return _priced_cover_option(covers, selected_id, period)

    def _guest_svc(
        self, session: AsyncSession, ussd: UssdSession, answers: dict[str, Any]
    ) -> GuestService:
        guest = ussd_guest_context(
            tenant_id=UUID(str(ussd.tenant_id)),
            guest_session_id=ussd.guest_session_id or ussd.id,
        )
        request = prepare_ussd_request(
            msisdn=str(answers.get("msisdn") or ""),
            correlation_id=ussd.correlation_id,
            guest=guest,
            is_test=ussd.is_test,
        )
        return GuestService(session, guest, get_insurance_provider(), request)

    def _phone(self, answers: dict[str, Any]) -> str:
        raw = normalize_msisdn(str(answers.get("msisdn") or ""))
        if not raw:
            raise ValidationAppError("Phone number missing from USSD session")
        candidate = f"+{raw}" if not raw.startswith("+") else raw
        return normalize_phone(candidate)

    async def _catalog(
        self, session: AsyncSession, ussd: UssdSession, answers: dict[str, Any]
    ) -> dict[str, Any]:
        """Serve products/makes only from our synced Definite catalog (memory/DB).

        Never wait on a live Definite products/makes call — that can exceed the
        USSD gateway timeout. Background refresh may be kicked if the snapshot
        is stale; the dialer still gets the stored rows immediately.
        """
        del ussd, answers  # catalog is tenant-global; MSISDN is unused here
        source = "memory"
        snapshot = insurer_catalog.recall()
        if snapshot is None or not snapshot.complete:
            source = "database"
            snapshot = await insurer_catalog.load_snapshot(session)
            if snapshot.complete:
                insurer_catalog.remember(snapshot)
        if snapshot is None or not snapshot.complete:
            raise ValidationAppError(
                "Products are updating. Please dial again in a moment."
            )
        try:
            from app.core.config import get_settings

            if (
                get_settings().insurer_catalog_background_refresh
                and insurer_catalog.is_stale(snapshot)
            ):
                insurer_catalog.schedule_refresh(
                    get_insurance_provider(), trigger="ussd-stale"
                )
        except Exception:
            pass
        return insurer_catalog.catalog_payload(snapshot, source)

    async def start(self, session: AsyncSession, ussd: UssdSession) -> WorkflowResult:
        answers = dict(ussd.answers or {})
        try:
            catalog = await self._catalog(session, ussd, answers)
        except ValidationAppError as exc:
            return WorkflowResult(
                message=str(getattr(exc, "message", None) or exc)[:160],
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                event_type=UssdEventType.BUSINESS_REJECTED.value,
                outcome=UssdOutcomeCategory.BUSINESS_FAILURE.value,
            )
        except Exception:
            return WorkflowResult(
                message="Could not load products. Please try again later.",
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                event_type=UssdEventType.TECHNICAL_ERROR.value,
                outcome=UssdOutcomeCategory.TECHNICAL_FAILURE.value,
            )
        categories = list(catalog.get("categories") or [])
        if not categories and catalog.get("products"):
            from app.integrations.insurance.catalog_stub import group_catalog

            categories = group_catalog(list(catalog.get("products") or []))
        if not categories:
            return WorkflowResult(
                message="No motor products available. Contact your agent.",
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                event_type=UssdEventType.BUSINESS_REJECTED.value,
                outcome=UssdOutcomeCategory.BUSINESS_FAILURE.value,
            )
        answers["category_offset"] = 0
        return self._prompt_categories(answers, categories, entered=True)

    async def handle(
        self, session: AsyncSession, ussd: UssdSession, text: str
    ) -> WorkflowResult:
        step = ussd.workflow_step or "category"
        answers = dict(ussd.answers or {})
        value = (text or "").strip()

        if step == "category":
            return await self._step_category(session, ussd, answers, value)
        if step == "product":
            return await self._step_product(session, ussd, answers, value)
        if step == "cover_option":
            return await self._step_cover_option(session, ussd, answers, value)
        if step == "cover_period":
            return await self._step_period(session, ussd, answers, value)
        if step == "make":
            return await self._step_make(session, ussd, answers, value)
        if step == "model":
            return await self._step_model(session, ussd, answers, value)
        if step == "id_number":
            return self._step_id(answers, value)
        if step == "full_name":
            return self._step_full_name(answers, value)
        if step == "email":
            return await self._step_email(session, ussd, answers, value)
        if step == "vehicle_registration":
            return self._step_registration(answers, value)
        if step == "chassis":
            return await self._step_chassis(session, ussd, answers, value)
        if step == "confirm":
            return await self._step_confirm(session, ussd, answers, value)
        return WorkflowResult(
            message="Session error. Dial again.",
            response_type=UssdResponseType.END.value,
            clear_workflow=True,
            event_type=UssdEventType.TECHNICAL_ERROR.value,
            outcome=UssdOutcomeCategory.TECHNICAL_FAILURE.value,
        )

    def _categories_from_catalog(self, catalog: dict[str, Any]) -> list[dict[str, Any]]:
        categories = list(catalog.get("categories") or [])
        if categories:
            return categories
        products = list(catalog.get("products") or [])
        if not products:
            return []
        from app.integrations.insurance.catalog_stub import group_catalog

        return group_catalog(products)

    def _products_in_category(
        self, catalog: dict[str, Any], category_name: str
    ) -> list[dict[str, Any]]:
        for group in self._categories_from_catalog(catalog):
            if str(group.get("category") or "") == category_name:
                return list(group.get("products") or [])
        return []

    def _prompt_categories(
        self,
        answers: dict[str, Any],
        categories: list[Any],
        *,
        entered: bool = False,
    ) -> WorkflowResult:
        offset = int(answers.get("category_offset") or 0)
        chunk, message, _ = _fit_menu_page(
            "Select class", categories, offset, label_fn=_category_label
        )
        answers["category_shown"] = len(chunk)
        return WorkflowResult(
            message=message,
            step="category",
            answers_patch=_answers_patch(answers),
            event_type=(
                UssdEventType.WORKFLOW_ENTERED.value
                if entered
                else UssdEventType.STEP_COMPLETED.value
            ),
            outcome=UssdOutcomeCategory.IN_PROGRESS.value,
        )

    async def _step_category(
        self,
        session: AsyncSession,
        ussd: UssdSession,
        answers: dict[str, Any],
        value: str,
    ) -> WorkflowResult:
        try:
            catalog = await self._catalog(session, ussd, answers)
        except ValidationAppError as exc:
            return WorkflowResult(
                message=str(getattr(exc, "message", None) or exc)[:160],
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                event_type=UssdEventType.BUSINESS_REJECTED.value,
                outcome=UssdOutcomeCategory.BUSINESS_FAILURE.value,
            )
        except Exception:
            return WorkflowResult(
                message="Could not load products. Please try again later.",
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                event_type=UssdEventType.TECHNICAL_ERROR.value,
                outcome=UssdOutcomeCategory.TECHNICAL_FAILURE.value,
            )
        categories = self._categories_from_catalog(catalog)
        offset = int(answers.get("category_offset") or 0)
        shown = int(answers.get("category_shown") or 0)
        if value == _MORE_KEY:
            if offset + shown >= len(categories):
                return WorkflowResult(
                    message="No more classes. Select a number from the list.",
                    step="category",
                    event_type=UssdEventType.VALIDATION_FAILED.value,
                    outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
                )
            answers["category_offset"] = offset + max(shown, 1)
            return self._prompt_categories(answers, categories)
        selected = _resolve_shown_choice(categories, offset, shown, value)
        if selected is None:
            return WorkflowResult(
                message=(
                    "Invalid option. Select a class number"
                    + (
                        f" or {_MORE_KEY} for more."
                        if offset + shown < len(categories)
                        else "."
                    )
                ),
                step="category",
                event_type=UssdEventType.VALIDATION_FAILED.value,
                outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
            )
        category_name = str(selected.get("category") or "")
        products = list(selected.get("products") or [])
        if not products:
            products = self._products_in_category(catalog, category_name)
        if not products:
            return WorkflowResult(
                message="No products in that class. Choose another.",
                step="category",
                event_type=UssdEventType.VALIDATION_FAILED.value,
                outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
            )
        answers["category"] = category_name
        answers["product_offset"] = 0
        return self._prompt_products(answers, products)

    def _prompt_products(
        self,
        answers: dict[str, Any],
        products: list[Any],
        *,
        entered: bool = False,
    ) -> WorkflowResult:
        offset = int(answers.get("product_offset") or 0)
        category = str(answers.get("category") or "Product")
        title = f"{category}"[:28] if category else "Select product"
        chunk, message, _ = _fit_menu_page(
            title, products, offset, label_fn=_product_label
        )
        answers["product_shown"] = len(chunk)
        return WorkflowResult(
            message=message,
            step="product",
            answers_patch=_answers_patch(answers),
            event_type=(
                UssdEventType.WORKFLOW_ENTERED.value
                if entered
                else UssdEventType.STEP_COMPLETED.value
            ),
            outcome=UssdOutcomeCategory.IN_PROGRESS.value,
        )

    async def _step_product(
        self,
        session: AsyncSession,
        ussd: UssdSession,
        answers: dict[str, Any],
        value: str,
    ) -> WorkflowResult:
        try:
            catalog = await self._catalog(session, ussd, answers)
        except ValidationAppError as exc:
            return WorkflowResult(
                message=str(getattr(exc, "message", None) or exc)[:160],
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                event_type=UssdEventType.BUSINESS_REJECTED.value,
                outcome=UssdOutcomeCategory.BUSINESS_FAILURE.value,
            )
        except Exception:
            return WorkflowResult(
                message="Could not load products. Please try again later.",
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                event_type=UssdEventType.TECHNICAL_ERROR.value,
                outcome=UssdOutcomeCategory.TECHNICAL_FAILURE.value,
            )
        category_name = str(answers.get("category") or "")
        products = self._products_in_category(catalog, category_name)
        if not products:
            products = list(catalog.get("products") or [])
        offset = int(answers.get("product_offset") or 0)
        shown = int(answers.get("product_shown") or 0)
        if value == _MORE_KEY:
            if offset + shown >= len(products):
                return WorkflowResult(
                    message="No more products. Select a number from the list.",
                    step="product",
                    event_type=UssdEventType.VALIDATION_FAILED.value,
                    outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
                )
            answers["product_offset"] = offset + max(shown, 1)
            return self._prompt_products(answers, products)
        selected = _resolve_shown_choice(products, offset, shown, value)
        if selected is None:
            return WorkflowResult(
                message=(
                    "Invalid option. Select a product number"
                    + (
                        f" or {_MORE_KEY} for more."
                        if offset + shown < len(products)
                        else "."
                    )
                ),
                step="product",
                event_type=UssdEventType.VALIDATION_FAILED.value,
                outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
            )
        covers = _visible_cover_options(
            [
                {"id": str(c.get("id") or ""), "name": str(c.get("name") or "")[:64]}
                for c in (selected.get("cover_options") or [])
            ]
        )
        if not covers:
            covers = [{"id": "1", "name": "Standard"}]
        answers["product"] = {
            "product_external_id": str(
                selected.get("external_id") or selected.get("code") or ""
            ),
            "product_code": str(selected.get("code") or selected.get("external_id") or ""),
            "product_name": str(selected.get("name") or "")[:64],
        }
        # Full list (incl. MONTHLY siblings) kept for pricedCoverOption parity with web.
        all_covers = list(selected.get("cover_options") or []) or covers
        answers["cover_option_ids"] = [
            {"id": str(c.get("id") or ""), "name": str(c.get("name") or "")[:64]}
            for c in all_covers
        ]
        answers["cover_offset"] = 0
        return self._prompt_covers(answers)

    def _prompt_covers(self, answers: dict[str, Any]) -> WorkflowResult:
        covers = _visible_cover_options(list(answers.get("cover_option_ids") or []))
        offset = int(answers.get("cover_offset") or 0)
        chunk, message, _ = _fit_menu_page(
            "Select cover", covers, offset, label_fn=_cover_label
        )
        answers["cover_shown"] = len(chunk)
        return WorkflowResult(
            message=message,
            step="cover_option",
            answers_patch=_answers_patch(answers),
            event_type=UssdEventType.STEP_COMPLETED.value,
        )

    async def _step_cover_option(
        self,
        session: AsyncSession,
        ussd: UssdSession,
        answers: dict[str, Any],
        value: str,
    ) -> WorkflowResult:
        covers = list(answers.get("cover_option_ids") or [])
        if not covers:
            # Recover covers from catalog if history restored without them.
            try:
                catalog = await self._catalog(session, ussd, answers)
            except Exception:
                catalog = {}
            product = answers.get("product") or {}
            ext = str(product.get("product_external_id") or "")
            for item in catalog.get("products") or []:
                if str(item.get("external_id") or item.get("code") or "") == ext:
                    answers["cover_option_ids"] = [
                        {
                            "id": str(c.get("id") or ""),
                            "name": str(c.get("name") or "")[:64],
                        }
                        for c in (item.get("cover_options") or [])
                    ]
                    break
        covers = _visible_cover_options(list(answers.get("cover_option_ids") or []))
        offset = int(answers.get("cover_offset") or 0)
        shown = int(answers.get("cover_shown") or 0)
        if value == _MORE_KEY:
            if offset + shown >= len(covers):
                return WorkflowResult(
                    message="No more covers. Select a listed number.",
                    step="cover_option",
                    event_type=UssdEventType.VALIDATION_FAILED.value,
                    outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
                )
            answers["cover_offset"] = offset + max(shown, 1)
            return self._prompt_covers(answers)
        selected = _resolve_shown_choice(covers, offset, shown, value)
        if selected is None:
            return WorkflowResult(
                message="Invalid option. Select a cover number.",
                step="cover_option",
                event_type=UssdEventType.VALIDATION_FAILED.value,
                outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
            )
        product = dict(answers.get("product") or {})
        product["cover_option_selected_id"] = str(selected.get("id") or "1")
        product["cover_option_name"] = _cover_display_name(str(selected.get("name") or ""))[
            :64
        ]
        answers["product"] = product
        lines = ["Select period"]
        for key, label in _COVER_PERIODS:
            lines.append(f"{key}. {label}")
        return WorkflowResult(
            message=_nav("\n".join(lines)),
            step="cover_period",
            answers_patch=_answers_patch(answers),
            event_type=UssdEventType.STEP_COMPLETED.value,
        )

    async def _step_period(
        self,
        session: AsyncSession,
        ussd: UssdSession,
        answers: dict[str, Any],
        value: str,
    ) -> WorkflowResult:
        period = next((label for key, label in _COVER_PERIODS if key == value), None)
        if period is None:
            return WorkflowResult(
                message="Invalid option. Select 1 or 2.",
                step="cover_period",
                event_type=UssdEventType.VALIDATION_FAILED.value,
                outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
            )
        answers["cover_period"] = period
        answers["make_offset"] = 0
        try:
            catalog = await self._catalog(session, ussd, answers)
        except Exception:
            return WorkflowResult(
                message="Vehicle makes unavailable. Try again later.",
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                event_type=UssdEventType.TECHNICAL_ERROR.value,
                outcome=UssdOutcomeCategory.TECHNICAL_FAILURE.value,
            )
        makes = list(catalog.get("makes") or [])
        if not makes:
            return WorkflowResult(
                message="Vehicle makes unavailable. Try again later.",
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                event_type=UssdEventType.TECHNICAL_ERROR.value,
                outcome=UssdOutcomeCategory.TECHNICAL_FAILURE.value,
            )
        return self._prompt_makes(answers, makes)

    def _prompt_makes(
        self, answers: dict[str, Any], makes: list[Any]
    ) -> WorkflowResult:
        offset = int(answers.get("make_offset") or 0)
        chunk, message, _ = _fit_menu_page(
            "Select make", makes, offset, label_fn=_make_label
        )
        answers["make_shown"] = len(chunk)
        return WorkflowResult(
            message=message,
            step="make",
            answers_patch=_answers_patch(answers),
            event_type=UssdEventType.STEP_COMPLETED.value,
        )

    async def _step_make(
        self,
        session: AsyncSession,
        ussd: UssdSession,
        answers: dict[str, Any],
        value: str,
    ) -> WorkflowResult:
        try:
            catalog = await self._catalog(session, ussd, answers)
        except Exception:
            return WorkflowResult(
                message="Vehicle makes unavailable. Try again later.",
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                event_type=UssdEventType.TECHNICAL_ERROR.value,
                outcome=UssdOutcomeCategory.TECHNICAL_FAILURE.value,
            )
        makes = list(catalog.get("makes") or [])
        if not makes:
            return WorkflowResult(
                message="Vehicle makes unavailable. Try again later.",
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                event_type=UssdEventType.TECHNICAL_ERROR.value,
                outcome=UssdOutcomeCategory.TECHNICAL_FAILURE.value,
            )
        offset = int(answers.get("make_offset") or 0)
        shown = int(answers.get("make_shown") or 0)
        if value == _MORE_KEY:
            if offset + shown >= len(makes):
                return WorkflowResult(
                    message="No more makes. Select a listed number.",
                    step="make",
                    event_type=UssdEventType.VALIDATION_FAILED.value,
                    outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
                )
            answers["make_offset"] = offset + max(shown, 1)
            return self._prompt_makes(answers, makes)
        selected = _resolve_shown_choice(makes, offset, shown, value)
        if selected is None:
            return WorkflowResult(
                message=f"Invalid option. Select a make or {_MORE_KEY} for more.",
                step="make",
                event_type=UssdEventType.VALIDATION_FAILED.value,
                outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
            )
        code = str(selected.get("external_id") or selected.get("code") or "")
        name = str(selected.get("name") or code)
        answers["vehicle_make"] = {"code": code, "name": name}
        answers["model_offset"] = 0
        models = list(selected.get("models") or []) or [{"id": code, "name": name}]
        return self._prompt_models(answers, models)

    def _prompt_models(
        self, answers: dict[str, Any], models: list[Any]
    ) -> WorkflowResult:
        offset = int(answers.get("model_offset") or 0)
        chunk, message, _ = _fit_menu_page(
            "Select model", models, offset, label_fn=_model_label
        )
        answers["model_shown"] = len(chunk)
        return WorkflowResult(
            message=message,
            step="model",
            answers_patch=_answers_patch(answers),
            event_type=UssdEventType.STEP_COMPLETED.value,
        )

    async def _models_for_make(
        self,
        session: AsyncSession,
        ussd: UssdSession,
        answers: dict[str, Any],
    ) -> list[dict[str, Any]]:
        make = answers.get("vehicle_make") or {}
        code = str(make.get("code") or "")
        try:
            catalog = await self._catalog(session, ussd, answers)
        except Exception:
            return []
        for item in catalog.get("makes") or []:
            item_code = str(item.get("external_id") or item.get("code") or "")
            if item_code == code:
                models = list(item.get("models") or [])
                return models or [{"id": code, "name": str(make.get("name") or code)}]
        return [{"id": code, "name": str(make.get("name") or code)}] if code else []

    async def _step_model(
        self,
        session: AsyncSession,
        ussd: UssdSession,
        answers: dict[str, Any],
        value: str,
    ) -> WorkflowResult:
        models = await self._models_for_make(session, ussd, answers)
        offset = int(answers.get("model_offset") or 0)
        shown = int(answers.get("model_shown") or 0)
        if value == _MORE_KEY:
            if offset + shown >= len(models):
                return WorkflowResult(
                    message="No more models. Select a listed number.",
                    step="model",
                    event_type=UssdEventType.VALIDATION_FAILED.value,
                    outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
                )
            answers["model_offset"] = offset + max(shown, 1)
            return self._prompt_models(answers, models)
        selected = _resolve_shown_choice(models, offset, shown, value)
        if selected is None:
            return WorkflowResult(
                message=f"Invalid option. Select a model or {_MORE_KEY} for more.",
                step="model",
                event_type=UssdEventType.VALIDATION_FAILED.value,
                outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
            )
        code = str(selected.get("id") or selected.get("code") or "")
        name = str(selected.get("name") or code)
        answers["vehicle_model"] = {"code": code, "name": name}
        return WorkflowResult(
            message=_nav("Enter ID or passport number"),
            step="id_number",
            answers_patch=_answers_patch(answers),
            event_type=UssdEventType.STEP_COMPLETED.value,
        )

    def _step_id(self, answers: dict[str, Any], value: str) -> WorkflowResult:
        if len(value) < 5:
            return WorkflowResult(
                message="Invalid ID. Enter at least 5 characters.",
                step="id_number",
                event_type=UssdEventType.VALIDATION_FAILED.value,
                outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
                error_category="INVALID_ID",
            )
        answers["id_number"] = value.strip().upper()
        return WorkflowResult(
            message=_nav("Enter full name (first and last)"),
            step="full_name",
            answers_patch=_answers_patch(answers),
            event_type=UssdEventType.STEP_COMPLETED.value,
        )

    def _step_full_name(self, answers: dict[str, Any], value: str) -> WorkflowResult:
        try:
            first, last = split_full_name(value)
        except ValidationAppError:
            return WorkflowResult(
                message="Enter full name with first and last name.",
                step="full_name",
                event_type=UssdEventType.VALIDATION_FAILED.value,
                outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
            )
        answers["first_name"] = first
        answers["last_name"] = last
        answers["full_name"] = f"{first} {last}"
        return WorkflowResult(
            message=_nav("Enter email for your certificate"),
            step="email",
            answers_patch=_answers_patch(answers),
            event_type=UssdEventType.STEP_COMPLETED.value,
        )

    async def _step_email(
        self,
        session: AsyncSession,
        ussd: UssdSession,
        answers: dict[str, Any],
        value: str,
    ) -> WorkflowResult:
        email = value.strip().lower()
        if "@" not in email or "." not in email.split("@")[-1] or len(email) < 6:
            return WorkflowResult(
                message="Invalid email. Try again (needed for certificate).",
                step="email",
                event_type=UssdEventType.VALIDATION_FAILED.value,
                outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
                error_category="INVALID_EMAIL",
            )
        answers["email"] = email[:254]
        service = self._guest_svc(session, ussd, answers)
        try:
            found = await service.lookup_returning_client(str(answers["id_number"]))
            if found and found.get("found"):
                ensured = await service.ensure_returning_client(str(answers["id_number"]))
                answers["returning"] = True
            else:
                ensured = await service.ensure_client(
                    IssuanceClientRequest(
                        first_name=str(answers["first_name"]),
                        last_name=str(answers["last_name"]),
                        id_number=str(answers["id_number"]),
                        phone=self._phone(answers),
                        email=email,
                    )
                )
                answers["returning"] = False
            local = (ensured or {}).get("local") or {}
            if local.get("id"):
                answers["customer_id"] = str(local["id"])
        except (ValidationAppError, StarServeError) as exc:
            return WorkflowResult(
                message=str(getattr(exc, "message", None) or exc)[:160],
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                answers_patch=_answers_patch(answers),
                event_type=UssdEventType.BUSINESS_REJECTED.value,
                outcome=UssdOutcomeCategory.BUSINESS_FAILURE.value,
                error_category="CLIENT_CREATE_FAILED",
            )
        except Exception:
            return WorkflowResult(
                message="Could not save your details. Please try again later.",
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                answers_patch=_answers_patch(answers),
                event_type=UssdEventType.TECHNICAL_ERROR.value,
                outcome=UssdOutcomeCategory.TECHNICAL_FAILURE.value,
            )
        return WorkflowResult(
            message=_nav("Enter vehicle registration"),
            step="vehicle_registration",
            answers_patch=_answers_patch(answers),
            event_type=UssdEventType.STEP_COMPLETED.value,
        )

    def _step_registration(self, answers: dict[str, Any], value: str) -> WorkflowResult:
        if len(value) < 3:
            return WorkflowResult(
                message="Invalid registration. Try again.",
                step="vehicle_registration",
                event_type=UssdEventType.VALIDATION_FAILED.value,
                outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
                error_category="INVALID_VEHICLE",
            )
        answers["vehicle_registration"] = value.strip().upper()
        return WorkflowResult(
            message=_nav("Enter chassis number"),
            step="chassis",
            answers_patch=_answers_patch(answers),
            event_type=UssdEventType.STEP_COMPLETED.value,
        )

    async def _step_chassis(
        self,
        session: AsyncSession,
        ussd: UssdSession,
        answers: dict[str, Any],
        value: str,
    ) -> WorkflowResult:
        chassis = value.strip().upper()
        if len(chassis) < 3:
            return WorkflowResult(
                message="Invalid chassis. Enter at least 3 characters.",
                step="chassis",
                event_type=UssdEventType.VALIDATION_FAILED.value,
                outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
            )
        answers["chassis_number"] = chassis[:64]
        product = dict(answers.get("product") or {})
        priced = self._priced_cover(answers)
        product["cover_option_id"] = str(priced.get("id") or "1")
        answers["product"] = product
        service = self._guest_svc(session, ussd, answers)
        period = str(answers.get("cover_period") or "Monthly")
        try:
            result = await service.calculate_premium(
                PremiumCalculateRequest(
                    sum_insured=0,
                    capacity=float(_DEFAULT_CAPACITY),
                    tonnage=0,
                    cover_period=period,
                    product=str(
                        product.get("product_external_id") or product.get("product_code")
                    ),
                    cover_option=str(priced.get("id") or "1"),
                    transaction_type="1",
                )
            )
        except (ValidationAppError, StarServeError) as exc:
            return WorkflowResult(
                message=str(getattr(exc, "message", None) or exc)[:160],
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                event_type=UssdEventType.BUSINESS_REJECTED.value,
                outcome=UssdOutcomeCategory.BUSINESS_FAILURE.value,
                error_category="PREMIUM_FAILED",
            )
        except Exception:
            return WorkflowResult(
                message="Could not calculate premium. Please try again later.",
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                event_type=UssdEventType.TECHNICAL_ERROR.value,
                outcome=UssdOutcomeCategory.TECHNICAL_FAILURE.value,
            )
        premium = result.get("premium") if isinstance(result, dict) else result
        gross = Decimal("0")
        if isinstance(premium, dict):
            raw = (
                premium.get("gross_premium")
                or premium.get("amount_payable")
                or premium.get("total")
                or 0
            )
            try:
                gross = Decimal(str(raw))
            except Exception:
                gross = Decimal("0")
            answers["premium_basic"] = str(premium.get("basic_premium") or "")
            answers["premium_phcf"] = str(premium.get("phcf") or "")
            answers["premium_training"] = str(premium.get("training_levy") or "")
            answers["premium_stamp"] = str(premium.get("stamp_duty") or "")
        referral = monthly_referral_cost(period)
        amount_due = (gross + referral).quantize(Decimal("0.01"))
        answers["gross_premium"] = str(gross)
        answers["referral_cost"] = str(referral)
        answers["amount_due"] = str(amount_due)
        answers["cover_period_used"] = period
        return WorkflowResult(
            message=_nav(self._confirm_text(answers)),
            step="confirm",
            answers_patch=_answers_patch(answers),
            event_type=UssdEventType.STEP_COMPLETED.value,
        )

    @staticmethod
    def _kes_display(raw: str | None) -> str:
        """Compact money for USSD — drop trailing .0 / .00 noise."""
        text = str(raw or "").strip()
        if not text or text == "—":
            return "—"
        try:
            value = Decimal(text)
        except Exception:
            return text[:12]
        if value == value.to_integral_value():
            return f"{int(value)}"
        return f"{value.quantize(Decimal('0.01'))}"

    def _confirm_text(self, answers: dict[str, Any]) -> str:
        """One-screen confirm: cover/period + total only, then Pay / Cancel.

        Birdview truncates long screens and shows a More page, which hides
        options 1/2. Keep this well under the ~160 char budget.
        """
        product = answers.get("product") or {}
        cover = str(
            product.get("cover_option_name") or product.get("product_name") or "Cover"
        )[:16]
        period = str(answers.get("cover_period") or "")[:10]
        amount_due = self._kes_display(
            str(answers.get("amount_due") or answers.get("gross_premium") or "—")
        )
        cover_line = " ".join(p for p in (cover, period) if p).strip() or "Cover"
        return "\n".join(
            [
                "Pay premium",
                cover_line,
                f"Total: KES {amount_due}",
                "1. Pay via M-Pesa",
                "2. Cancel",
            ]
        )

    async def _step_confirm(
        self,
        session: AsyncSession,
        ussd: UssdSession,
        answers: dict[str, Any],
        value: str,
    ) -> WorkflowResult:
        if value == "2":
            return WorkflowResult(
                message="Payment cancelled. Dial again when ready.",
                response_type=UssdResponseType.END.value,
                answers_patch=_answers_patch(answers),
                clear_workflow=True,
                event_type=UssdEventType.SESSION_TERMINATED.value,
                outcome=UssdOutcomeCategory.NAVIGATION.value,
            )
        if value != "1":
            return WorkflowResult(
                message="Select 1 to pay or 2 to cancel.",
                step="confirm",
                event_type=UssdEventType.VALIDATION_FAILED.value,
                outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
            )
        return await self._submit_and_pay(session, ussd, answers)

    async def _submit_and_pay(
        self,
        session: AsyncSession,
        ussd: UssdSession,
        answers: dict[str, Any],
    ) -> WorkflowResult:
        product = dict(answers.get("product") or {})
        make = answers.get("vehicle_make") or {}
        model = answers.get("vehicle_model") or {}
        customer_id = str(answers.get("customer_id") or "")
        if not customer_id:
            return WorkflowResult(
                message="Client profile missing. Dial again to restart.",
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                event_type=UssdEventType.TECHNICAL_ERROR.value,
                outcome=UssdOutcomeCategory.TECHNICAL_FAILURE.value,
            )
        priced = self._priced_cover(answers)
        product["cover_option_id"] = str(priced.get("id") or "1")
        period = str(answers.get("cover_period") or "Monthly")
        service = self._guest_svc(session, ussd, answers)
        year = date.today().year - 5
        try:
            phone = self._phone(answers)
            submitted = await service.submit(
                IssuanceSubmitRequest(
                    customer_id=customer_id,
                    product_external_id=str(product.get("product_external_id") or ""),
                    product_code=str(product.get("product_code") or ""),
                    product_name=(
                        str(product["product_name"])
                        if product.get("product_name")
                        else None
                    ),
                    cover_option_id=str(priced.get("id") or "1"),
                    cover_option_name=(
                        str(product["cover_option_name"])
                        if product.get("cover_option_name")
                        else None
                    ),
                    cover_period=period,
                    cover_period_used=period,
                    capacity=_DEFAULT_CAPACITY,
                    tonnage=Decimal("0"),
                    sum_insured=Decimal("0"),
                    vehicle_registration=str(answers.get("vehicle_registration") or ""),
                    vehicle_make_code=str(make.get("code") or ""),
                    vehicle_make_name=str(make.get("name") or ""),
                    vehicle_model_code=str(model.get("code") or ""),
                    vehicle_model_name=str(model.get("name") or ""),
                    vehicle_year=year,
                    chassis_number=str(answers.get("chassis_number") or ""),
                    engine_rating=1500,
                )
            )
            policy = (submitted or {}).get("policy") or {}
            policy_id = str(policy.get("id") or "")
            if not policy_id:
                raise ValidationAppError("Policy was not created")
            answers["policy_id"] = policy_id
            policy_number = str(policy.get("policy_number") or policy.get("number") or "")
            if policy_number:
                answers["policy_number"] = policy_number
            paid = await service.pay(
                IssuancePayRequest(policy_id=policy_id, method="BIRDVIEW", phone=phone)
            )
        except (ValidationAppError, StarServeError) as exc:
            return WorkflowResult(
                message=str(getattr(exc, "message", None) or exc)[:160],
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                answers_patch=_answers_patch(answers),
                event_type=UssdEventType.BUSINESS_REJECTED.value,
                outcome=UssdOutcomeCategory.BUSINESS_FAILURE.value,
                error_category="PAY_FAILED",
            )
        except Exception:
            return WorkflowResult(
                message="Could not start payment. Try again or use the website.",
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                answers_patch=_answers_patch(answers),
                event_type=UssdEventType.TECHNICAL_ERROR.value,
                outcome=UssdOutcomeCategory.TECHNICAL_FAILURE.value,
            )

        cert_note = ""
        if isinstance(paid, dict) and (paid.get("certificate") or {}).get("id"):
            cert_note = " Certificate will be emailed when paid."
        policy_bit = (
            f" {answers['policy_number']}" if answers.get("policy_number") else ""
        )
        due = answers.get("amount_due") or answers.get("gross_premium")
        return WorkflowResult(
            message=(
                f"M-Pesa sent for KES {due}{policy_bit}."
                f"{cert_note} Thank you."
            ),
            response_type=UssdResponseType.END.value,
            answers_patch=_answers_patch(answers),
            clear_workflow=True,
            event_type=UssdEventType.WORKFLOW_SUCCEEDED.value,
            outcome=UssdOutcomeCategory.SUCCESS.value,
        )
