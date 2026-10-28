"""USSD menu engine — navigation, config pinning, workflow dispatch, idempotency."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.modules.ussd.enums import (
    UssdConfigStatus,
    UssdEventType,
    UssdOutcomeCategory,
    UssdResponseType,
    UssdSessionStatus,
)
from app.modules.ussd.events import record_event
from app.modules.ussd.models import (
    UssdAdminAudit,
    UssdIdempotencyRecord,
    UssdMenuConfig,
    UssdProviderSetting,
    UssdSession,
)
from app.modules.ussd.navigation import NavCommand, NavPolicy, classify_navigation
from app.modules.ussd.privacy import hash_msisdn, mask_msisdn, normalize_msisdn
from app.modules.ussd.seed import default_menu_definition, render_menu_text
from app.modules.ussd.workflows import get_workflow


class EngineResponse:
    __slots__ = ("text", "response_type", "session_id", "is_new")

    def __init__(
        self,
        *,
        text: str,
        response_type: str,
        session_id: UUID | None = None,
        is_new: bool = False,
    ) -> None:
        self.text = text
        self.response_type = response_type
        self.session_id = session_id
        self.is_new = is_new


async def ensure_published_config(
    session: AsyncSession, tenant_id: UUID
) -> UssdMenuConfig:
    row = await session.scalar(
        select(UssdMenuConfig)
        .where(
            UssdMenuConfig.tenant_id == tenant_id,
            UssdMenuConfig.status == UssdConfigStatus.PUBLISHED.value,
        )
        .order_by(UssdMenuConfig.version.desc())
        .limit(1)
    )
    if row is not None:
        return row
    definition = default_menu_definition()
    row = UssdMenuConfig(
        tenant_id=tenant_id,
        version=1,
        status=UssdConfigStatus.PUBLISHED.value,
        name="Default StarServe menu",
        welcome_text=definition["screens"]["main"]["title"],
        root_screen_key="main",
        definition=definition,
        published_at=datetime.now(UTC),
    )
    session.add(row)
    await session.flush()
    session.add(
        UssdAdminAudit(
            tenant_id=tenant_id,
            actor_user_id=None,
            action="ussd.config_publish",
            resource="ussd_menu_config",
            resource_id=str(row.id),
            detail={"version": row.version, "source": "system_seed"},
        )
    )
    await session.flush()
    return row


async def resolve_provider(
    session: AsyncSession, *, service_code: str
) -> UssdProviderSetting | None:
    from app.modules.ussd.providers.birdview import normalize_ussd_code

    code = normalize_ussd_code(service_code)
    if not code:
        return None
    row = await session.scalar(
        select(UssdProviderSetting).where(
            UssdProviderSetting.service_code == code,
            UssdProviderSetting.enabled.is_(True),
        )
    )
    if row is not None:
        return row
    # Tolerate stored codes without * / # wrappers.
    return await session.scalar(
        select(UssdProviderSetting).where(
            UssdProviderSetting.enabled.is_(True),
            UssdProviderSetting.service_code.in_(
                {
                    code,
                    code.strip("*#"),
                    f"*{code.strip('*#')}#",
                    service_code.strip(),
                }
            ),
        )
    )


class UssdEngine:
    async def handle(
        self,
        session: AsyncSession,
        *,
        tenant_id: UUID,
        provider_kind: str,
        provider_session_id: str,
        service_code: str,
        msisdn: str,
        text: str | None,
        correlation_id: str,
        is_test: bool = False,
        idempotency_key: str | None = None,
    ) -> EngineResponse:
        now = datetime.now(UTC)
        if idempotency_key:
            prior = await session.scalar(
                select(UssdIdempotencyRecord).where(
                    UssdIdempotencyRecord.tenant_id == tenant_id,
                    UssdIdempotencyRecord.idempotency_key == idempotency_key,
                )
            )
            if prior is not None and prior.expires_at > now:
                await record_event(
                    session,
                    tenant_id=tenant_id,
                    session_id=prior.session_id or uuid4(),
                    event_type=UssdEventType.DUPLICATE_CALLBACK.value,
                    event_key=f"dup:{idempotency_key}",
                    correlation_id=correlation_id,
                    is_test=is_test,
                    outcome=UssdOutcomeCategory.IN_PROGRESS.value,
                )
                return EngineResponse(
                    text=prior.response_text,
                    response_type=prior.response_type,
                    session_id=prior.session_id,
                )

        config = await ensure_published_config(session, tenant_id)
        msisdn_n = normalize_msisdn(msisdn)
        msisdn_h = hash_msisdn(msisdn_n)
        ussd = await session.scalar(
            select(UssdSession).where(
                UssdSession.tenant_id == tenant_id,
                UssdSession.provider_session_id == provider_session_id,
            )
        )
        is_new = False
        expired_active = (
            ussd is not None
            and ussd.status == UssdSessionStatus.ACTIVE.value
            and ussd.expires_at <= now
        )
        needs_fresh = ussd is None or ussd.status != UssdSessionStatus.ACTIVE.value or expired_active
        if needs_fresh:
            if expired_active and ussd is not None:
                ussd.status = UssdSessionStatus.TIMED_OUT.value
                ussd.termination_reason = "EXPIRED"
                ussd.completed_at = now
                await record_event(
                    session,
                    tenant_id=tenant_id,
                    session_id=ussd.id,
                    event_type=UssdEventType.SESSION_TIMED_OUT.value,
                    config_version=ussd.config_version,
                    msisdn_hash=ussd.msisdn_hash,
                    is_test=ussd.is_test,
                    outcome=UssdOutcomeCategory.TIMED_OUT.value,
                )
            # Reuse the row when SESSIONID collides (unique tenant+provider_session_id).
            if ussd is None:
                ussd = UssdSession(
                    tenant_id=tenant_id,
                    config_id=config.id,
                    config_version=config.version,
                    provider_kind=provider_kind,
                    provider_session_id=provider_session_id,
                    service_code=service_code or "",
                    msisdn_hash=msisdn_h,
                    msisdn_masked=mask_msisdn(msisdn_n),
                    status=UssdSessionStatus.ACTIVE.value,
                    is_test=is_test,
                    current_screen_key=config.root_screen_key,
                    answers={"msisdn": msisdn_n},
                    history=[],
                    correlation_id=correlation_id,
                    guest_session_id=uuid4(),
                    expires_at=now + timedelta(seconds=config.session_ttl_seconds or 180),
                )
                session.add(ussd)
            else:
                ussd.config_id = config.id
                ussd.config_version = config.version
                ussd.provider_kind = provider_kind
                ussd.service_code = service_code or ""
                ussd.msisdn_hash = msisdn_h
                ussd.msisdn_masked = mask_msisdn(msisdn_n)
                ussd.status = UssdSessionStatus.ACTIVE.value
                ussd.is_test = is_test
                ussd.current_screen_key = config.root_screen_key
                ussd.workflow_action = None
                ussd.workflow_step = None
                ussd.answers = {"msisdn": msisdn_n}
                ussd.history = []
                ussd.invalid_attempts = 0
                ussd.correlation_id = correlation_id
                ussd.guest_session_id = uuid4()
                ussd.completed_at = None
                ussd.termination_reason = None
                ussd.last_message = None
                ussd.last_response_type = None
                ussd.expires_at = now + timedelta(seconds=config.session_ttl_seconds or 180)
                ussd.version = int(ussd.version or 0) + 1
                flag_modified(ussd, "answers")
                flag_modified(ussd, "history")
            await session.flush()
            is_new = True
            await record_event(
                session,
                tenant_id=tenant_id,
                session_id=ussd.id,
                event_type=UssdEventType.SESSION_STARTED.value,
                event_key=f"start:{ussd.id}",
                config_version=config.version,
                screen_key=ussd.current_screen_key,
                provider_kind=provider_kind,
                correlation_id=correlation_id,
                msisdn_hash=msisdn_h,
                is_test=is_test,
                outcome=UssdOutcomeCategory.IN_PROGRESS.value,
            )
        else:
            ussd.expires_at = now + timedelta(seconds=config.session_ttl_seconds or 180)
            ussd.version += 1
            await record_event(
                session,
                tenant_id=tenant_id,
                session_id=ussd.id,
                event_type=UssdEventType.SESSION_RESUMED.value,
                event_key=f"resume:{ussd.id}:{ussd.version}",
                config_version=ussd.config_version,
                screen_key=ussd.current_screen_key,
                workflow_action=ussd.workflow_action,
                step_id=ussd.workflow_step,
                provider_kind=provider_kind,
                correlation_id=correlation_id,
                msisdn_hash=msisdn_h,
                is_test=is_test,
                outcome=UssdOutcomeCategory.IN_PROGRESS.value,
            )

        # Pin to the session's config version (not necessarily latest publish).
        pinned = await session.get(UssdMenuConfig, ussd.config_id)
        if pinned is None:
            pinned = config
        definition = pinned.definition or default_menu_definition()
        policy = NavPolicy(
            back=pinned.nav_back or "0",
            home=pinned.nav_home or "00",
            repeat=pinned.nav_repeat,
        )
        # Birdview ~160 char screen budget; legacy rows may still store 182.
        max_chars = min(int(pinned.max_message_chars or 160), 160)

        # Empty INPUT => welcome on new session; on resume redisplay last screen.
        if not (text or "").strip():
            if is_new:
                msg = self._main_menu_text(definition, pinned, max_chars=max_chars)
                return await self._finish(
                    session,
                    ussd,
                    pinned,
                    text=msg,
                    response_type=UssdResponseType.CONTINUE.value,
                    idempotency_key=idempotency_key,
                    event_type=UssdEventType.MENU_SHOWN.value,
                )
            msg = ussd.last_message or self._main_menu_text(definition, pinned, max_chars=max_chars)
            return await self._finish(
                session,
                ussd,
                pinned,
                text=msg,
                response_type=UssdResponseType.CONTINUE.value,
                idempotency_key=idempotency_key,
                event_type=UssdEventType.NAV_REPEAT.value,
            )

        screen = self._screen(definition, ussd.current_screen_key)
        field_type = None
        if ussd.workflow_action and ussd.workflow_step:
            # Workflow data-entry steps — treat as INPUT for nav safety.
            field_type = self._infer_field_type(ussd.workflow_step)
        at_root = (
            not ussd.workflow_action
            and ussd.current_screen_key == (pinned.root_screen_key or "main")
        )
        nav = classify_navigation(
            text,
            policy=policy,
            screen_type="INPUT" if ussd.workflow_action else screen.get("type", "MENU"),
            expected_field_type=field_type,
            at_root=at_root,
        )

        if nav == NavCommand.HOME:
            return await self._go_home(
                session, ussd, pinned, definition, max_chars, idempotency_key
            )
        if nav == NavCommand.BACK:
            return await self._go_back(
                session, ussd, pinned, definition, max_chars, idempotency_key
            )
        if nav == NavCommand.REPEAT:
            msg = ussd.last_message or self._main_menu_text(definition, pinned, max_chars)
            return await self._finish(
                session,
                ussd,
                pinned,
                text=msg,
                response_type=UssdResponseType.CONTINUE.value,
                idempotency_key=idempotency_key,
                event_type=UssdEventType.NAV_REPEAT.value,
            )

        if ussd.workflow_action:
            return await self._workflow_input(
                session, ussd, pinned, definition, text or "", max_chars, idempotency_key
            )

        return await self._menu_select(
            session, ussd, pinned, definition, text or "", max_chars, idempotency_key
        )

    def _screen(self, definition: dict[str, Any], key: str) -> dict[str, Any]:
        screens = definition.get("screens") or {}
        return dict(screens.get(key) or screens.get("main") or {})

    def _main_menu_text(
        self, definition: dict[str, Any], config: UssdMenuConfig, *, max_chars: int
    ) -> str:
        screen = self._screen(definition, config.root_screen_key or "main")
        # Root has nowhere to go back — never show nav footer on the main menu.
        screen = {**screen, "footer": ""}
        if config.welcome_text:
            screen = {**screen, "title": config.welcome_text}
        return render_menu_text(screen, max_chars=max_chars)

    def _infer_field_type(self, step: str) -> str:
        mapping = {
            "id_number": "ID_NUMBER",
            "vehicle_registration": "VEHICLE_REG",
            "claim_number": "CLAIM_REF",
            "policy_number": "POLICY_REF",
            "incident_date": "DATE",
            "incident_location": "TEXT",
            "incident_description": "TEXT",
            "full_name": "TEXT",
            "email": "TEXT",
            "phone": "PHONE",
            "chassis": "TEXT",
            "confirm": "MENU_CHOICE",
            "category": "MENU_CHOICE",
            "product": "MENU_CHOICE",
            "cover_option": "MENU_CHOICE",
            "cover_period": "MENU_CHOICE",
            "make": "MENU_CHOICE",
            "model": "MENU_CHOICE",
        }
        return mapping.get(step, "TEXT")

    async def _menu_select(
        self,
        session: AsyncSession,
        ussd: UssdSession,
        config: UssdMenuConfig,
        definition: dict[str, Any],
        text: str,
        max_chars: int,
        idempotency_key: str | None,
    ) -> EngineResponse:
        screen = self._screen(definition, ussd.current_screen_key)
        options = [
            o for o in (screen.get("options") or []) if o.get("active", True)
        ]
        choice = next((o for o in options if str(o.get("key")) == text.strip()), None)
        if choice is None:
            ussd.invalid_attempts += 1
            keys = ", ".join(str(o.get("key")) for o in options) or "a listed option"
            msg = f"Invalid option. Select {keys}."
            if ussd.invalid_attempts >= (config.max_invalid_attempts or 3):
                msg = (definition.get("messages") or {}).get(
                    "too_many_errors", "Too many invalid attempts. Please dial again."
                )
                ussd.status = UssdSessionStatus.TERMINATED.value
                ussd.termination_reason = "MAX_INVALID"
                ussd.completed_at = datetime.now(UTC)
                return await self._finish(
                    session,
                    ussd,
                    config,
                    text=msg,
                    response_type=UssdResponseType.END.value,
                    idempotency_key=idempotency_key,
                    event_type=UssdEventType.SESSION_TERMINATED.value,
                    outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
                )
            return await self._finish(
                session,
                ussd,
                config,
                text=msg,
                response_type=UssdResponseType.CONTINUE.value,
                idempotency_key=idempotency_key,
                event_type=UssdEventType.VALIDATION_FAILED.value,
                outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
            )

        ussd.invalid_attempts = 0
        dest = choice.get("destination_screen")
        action = choice.get("workflow_action")
        self._push_history(ussd)
        if dest:
            ussd.current_screen_key = str(dest)
            msg = render_menu_text(self._screen(definition, str(dest)), max_chars=max_chars)
            return await self._finish(
                session,
                ussd,
                config,
                text=msg,
                response_type=UssdResponseType.CONTINUE.value,
                idempotency_key=idempotency_key,
                event_type=UssdEventType.OPTION_SELECTED.value,
            )
        if action:
            handler = get_workflow(str(action))
            if handler is None:
                return await self._finish(
                    session,
                    ussd,
                    config,
                    text="Service unavailable. Please try again later.",
                    response_type=UssdResponseType.END.value,
                    idempotency_key=idempotency_key,
                    event_type=UssdEventType.TECHNICAL_ERROR.value,
                    outcome=UssdOutcomeCategory.TECHNICAL_FAILURE.value,
                )
            ussd.workflow_action = str(action)
            result = await handler.start(session, ussd)
            return await self._apply_workflow_result(
                session, ussd, config, result, idempotency_key
            )
        msg = self._main_menu_text(definition, config, max_chars=max_chars)
        return await self._finish(
            session,
            ussd,
            config,
            text=msg,
            response_type=UssdResponseType.CONTINUE.value,
            idempotency_key=idempotency_key,
        )

    async def _workflow_input(
        self,
        session: AsyncSession,
        ussd: UssdSession,
        config: UssdMenuConfig,
        definition: dict[str, Any],
        text: str,
        max_chars: int,
        idempotency_key: str | None,
    ) -> EngineResponse:
        handler = get_workflow(ussd.workflow_action)
        if handler is None:
            return await self._go_home(
                session, ussd, config, definition, max_chars, idempotency_key
            )
        self._push_history(ussd)
        result = await handler.handle(session, ussd, text)
        if result.outcome == UssdOutcomeCategory.VALIDATION_FAILURE.value:
            ussd.invalid_attempts += 1
            if ussd.invalid_attempts >= (config.max_invalid_attempts or 3):
                msg = (definition.get("messages") or {}).get(
                    "too_many_errors", "Too many invalid attempts. Please dial again."
                )
                ussd.status = UssdSessionStatus.TERMINATED.value
                ussd.termination_reason = "MAX_INVALID"
                ussd.completed_at = datetime.now(UTC)
                return await self._finish(
                    session,
                    ussd,
                    config,
                    text=msg,
                    response_type=UssdResponseType.END.value,
                    idempotency_key=idempotency_key,
                    event_type=UssdEventType.SESSION_TERMINATED.value,
                    outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
                )
        else:
            ussd.invalid_attempts = 0
        return await self._apply_workflow_result(
            session, ussd, config, result, idempotency_key
        )

    async def _apply_workflow_result(
        self,
        session: AsyncSession,
        ussd: UssdSession,
        config: UssdMenuConfig,
        result: Any,
        idempotency_key: str | None,
    ) -> EngineResponse:
        if result.answers_patch:
            answers = dict(ussd.answers or {})
            answers.update(result.answers_patch)
            ussd.answers = answers
            flag_modified(ussd, "answers")
        if result.step is not None:
            ussd.workflow_step = result.step
        if result.clear_workflow or result.response_type == UssdResponseType.END.value:
            if result.clear_workflow:
                ussd.workflow_action = None
                ussd.workflow_step = None
            if result.response_type == UssdResponseType.END.value:
                ussd.status = (
                    UssdSessionStatus.COMPLETED.value
                    if result.outcome == UssdOutcomeCategory.SUCCESS.value
                    else UssdSessionStatus.FAILED.value
                    if result.outcome
                    in {
                        UssdOutcomeCategory.TECHNICAL_FAILURE.value,
                        UssdOutcomeCategory.BUSINESS_FAILURE.value,
                    }
                    else UssdSessionStatus.COMPLETED.value
                )
                ussd.completed_at = datetime.now(UTC)
                ussd.termination_reason = result.outcome or "COMPLETED"
        return await self._finish(
            session,
            ussd,
            config,
            text=result.message,
            response_type=result.response_type,
            idempotency_key=idempotency_key,
            event_type=result.event_type,
            outcome=result.outcome,
            error_category=result.error_category,
        )

    async def _go_home(
        self,
        session: AsyncSession,
        ussd: UssdSession,
        config: UssdMenuConfig,
        definition: dict[str, Any],
        max_chars: int,
        idempotency_key: str | None,
    ) -> EngineResponse:
        ussd.workflow_action = None
        ussd.workflow_step = None
        ussd.current_screen_key = config.root_screen_key or "main"
        ussd.invalid_attempts = 0
        ussd.history = []
        flag_modified(ussd, "history")
        # Keep msisdn only — drop workflow answers to avoid cross-workflow leakage.
        msisdn = (ussd.answers or {}).get("msisdn")
        ussd.answers = {"msisdn": msisdn} if msisdn else {}
        flag_modified(ussd, "answers")
        msg = self._main_menu_text(definition, config, max_chars=max_chars)
        return await self._finish(
            session,
            ussd,
            config,
            text=msg,
            response_type=UssdResponseType.CONTINUE.value,
            idempotency_key=idempotency_key,
            event_type=UssdEventType.NAV_HOME.value,
            outcome=UssdOutcomeCategory.NAVIGATION.value,
        )

    async def _go_back(
        self,
        session: AsyncSession,
        ussd: UssdSession,
        config: UssdMenuConfig,
        definition: dict[str, Any],
        max_chars: int,
        idempotency_key: str | None,
    ) -> EngineResponse:
        history = list(ussd.history or [])
        if not history:
            return await self._go_home(
                session, ussd, config, definition, max_chars, idempotency_key
            )
        prev = history.pop()
        ussd.history = history
        flag_modified(ussd, "history")
        ussd.current_screen_key = prev.get("screen_key") or config.root_screen_key
        ussd.workflow_action = prev.get("workflow_action")
        ussd.workflow_step = prev.get("workflow_step")
        if prev.get("answers") is not None:
            ussd.answers = dict(prev["answers"])
            flag_modified(ussd, "answers")
        if ussd.workflow_action and ussd.workflow_step:
            # Re-prompt current step via handler start/last message pattern.
            handler = get_workflow(ussd.workflow_action)
            if handler and not ussd.workflow_step:
                result = await handler.start(session, ussd)
                return await self._apply_workflow_result(
                    session, ussd, config, result, idempotency_key
                )
            msg = prev.get("message") or ussd.last_message or "Enter your response"
            return await self._finish(
                session,
                ussd,
                config,
                text=str(msg),
                response_type=UssdResponseType.CONTINUE.value,
                idempotency_key=idempotency_key,
                event_type=UssdEventType.NAV_BACK.value,
                outcome=UssdOutcomeCategory.NAVIGATION.value,
            )
        msg = render_menu_text(
            self._screen(definition, ussd.current_screen_key), max_chars=max_chars
        )
        return await self._finish(
            session,
            ussd,
            config,
            text=msg,
            response_type=UssdResponseType.CONTINUE.value,
            idempotency_key=idempotency_key,
            event_type=UssdEventType.NAV_BACK.value,
            outcome=UssdOutcomeCategory.NAVIGATION.value,
        )

    def _push_history(self, ussd: UssdSession) -> None:
        history = list(ussd.history or [])
        history.append(
            {
                "screen_key": ussd.current_screen_key,
                "workflow_action": ussd.workflow_action,
                "workflow_step": ussd.workflow_step,
                "answers": dict(ussd.answers or {}),
                "message": ussd.last_message,
            }
        )
        ussd.history = history[-20:]
        flag_modified(ussd, "history")

    async def _finish(
        self,
        session: AsyncSession,
        ussd: UssdSession,
        config: UssdMenuConfig,
        *,
        text: str,
        response_type: str,
        idempotency_key: str | None,
        event_type: str | None = None,
        outcome: str | None = None,
        error_category: str | None = None,
    ) -> EngineResponse:
        max_chars = min(int(config.max_message_chars or 160), 160)
        if len(text) > max_chars:
            text = text[: max_chars - 1].rstrip() + "…"
        ussd.last_message = text
        ussd.last_response_type = response_type
        if event_type:
            await record_event(
                session,
                tenant_id=ussd.tenant_id,
                session_id=ussd.id,
                event_type=event_type,
                # Compact key: dashed UUID + long event names exceeded varchar(64).
                event_key=f"{event_type}:{ussd.id.hex}:{ussd.version}:{uuid4().hex[:8]}",
                workflow_action=ussd.workflow_action,
                step_id=ussd.workflow_step,
                screen_key=ussd.current_screen_key,
                config_version=ussd.config_version,
                outcome=outcome,
                error_category=error_category,
                provider_kind=ussd.provider_kind,
                correlation_id=ussd.correlation_id,
                msisdn_hash=ussd.msisdn_hash,
                is_test=ussd.is_test,
            )
        if idempotency_key:
            session.add(
                UssdIdempotencyRecord(
                    tenant_id=ussd.tenant_id,
                    idempotency_key=idempotency_key,
                    session_id=ussd.id,
                    response_type=response_type,
                    response_text=text,
                    expires_at=datetime.now(UTC) + timedelta(minutes=10),
                )
            )
        await session.flush()
        return EngineResponse(
            text=text,
            response_type=response_type,
            session_id=ussd.id,
            is_new=False,
        )
