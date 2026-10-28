"""Admin configuration, publish, provider settings, session inspection."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.config.settings import get_settings
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationAppError
from app.core.security.context import SecurityContext
from app.modules.audit.service import AuditService
from app.modules.ussd.enums import REGISTERED_WORKFLOWS, UssdConfigStatus, UssdProviderKind
from app.modules.users.models import User
from app.modules.ussd.models import (
    UssdAdminAudit,
    UssdMenuConfig,
    UssdProviderSetting,
    UssdSession,
)
from app.modules.ussd.seed import default_menu_definition


class UssdAdminService:
    def __init__(self, session: AsyncSession, ctx: SecurityContext) -> None:
        self.session = session
        self.ctx = ctx

    @staticmethod
    def _audit_message(action: str, detail: dict) -> str | None:
        version = detail.get("version")
        if action == "ussd.config_publish":
            return f"Published menu version {version}" if version is not None else "Published USSD menu"
        if action == "ussd.config_create":
            return f"Created menu draft version {version}" if version is not None else "Created USSD menu draft"
        if action == "ussd.config_update":
            fields = detail.get("fields")
            if isinstance(fields, list) and fields:
                return f"Updated menu draft ({', '.join(str(f) for f in fields[:4])})"
            return "Updated USSD menu draft"
        if action == "ussd.provider_update":
            return "Updated USSD provider settings"
        return None

    async def _audit(self, action: str, resource: str, resource_id: str | None, detail: dict) -> None:
        self.session.add(
            UssdAdminAudit(
                tenant_id=self.ctx.tenant_id,
                actor_user_id=self.ctx.user_id,
                action=action,
                resource=resource,
                resource_id=resource_id,
                detail=detail,
            )
        )
        await self.session.flush()
        await AuditService(self.session).record(
            action=action,
            resource=resource,
            resource_id=resource_id,
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            metadata=detail,
            message=self._audit_message(action, detail),
            flush=True,
        )

    async def list_configs(self) -> list[UssdMenuConfig]:
        rows = await self.session.scalars(
            select(UssdMenuConfig)
            .where(UssdMenuConfig.tenant_id == self.ctx.tenant_id)
            .order_by(UssdMenuConfig.version.desc())
        )
        return list(rows)

    async def get_published(self) -> UssdMenuConfig | None:
        return await self.session.scalar(
            select(UssdMenuConfig)
            .where(
                UssdMenuConfig.tenant_id == self.ctx.tenant_id,
                UssdMenuConfig.status == UssdConfigStatus.PUBLISHED.value,
            )
            .order_by(UssdMenuConfig.version.desc())
            .limit(1)
        )

    async def get_config(self, config_id: UUID) -> UssdMenuConfig:
        row = await self.session.get(UssdMenuConfig, config_id)
        if row is None or row.tenant_id != self.ctx.tenant_id:
            raise ResourceNotFoundError("USSD menu configuration not found")
        return row

    async def create_draft(self, *, name: str, from_published: bool = True) -> UssdMenuConfig:
        published = await self.get_published()
        latest = await self.session.scalar(
            select(UssdMenuConfig.version)
            .where(UssdMenuConfig.tenant_id == self.ctx.tenant_id)
            .order_by(UssdMenuConfig.version.desc())
            .limit(1)
        )
        version = int(latest or 0) + 1
        if from_published and published is not None:
            definition = dict(published.definition or {})
            welcome = published.welcome_text
            root = published.root_screen_key
        else:
            definition = default_menu_definition()
            welcome = definition["screens"]["main"]["title"]
            root = "main"
        row = UssdMenuConfig(
            tenant_id=self.ctx.tenant_id,
            version=version,
            status=UssdConfigStatus.DRAFT.value,
            name=name[:128],
            welcome_text=welcome,
            root_screen_key=root,
            definition=definition,
            created_by=self.ctx.user_id,
        )
        self.session.add(row)
        await self.session.flush()
        await self._audit("ussd.config_create", "ussd_menu_config", str(row.id), {"version": version})
        return row

    def _validate_definition(self, definition: dict[str, Any], root_key: str) -> None:
        screens = definition.get("screens") or {}
        if root_key not in screens:
            raise ValidationAppError("Root screen is missing from the menu definition")
        main = screens[root_key]
        options = [o for o in (main.get("options") or []) if o.get("active", True)]
        if not options:
            raise ValidationAppError("Main menu must have at least one active option")
        keys = [str(o.get("key")) for o in options]
        if len(keys) != len(set(keys)):
            raise ValidationAppError("Duplicate active option keys are not allowed")
        for opt in options:
            action = opt.get("workflow_action")
            dest = opt.get("destination_screen")
            if action and action not in REGISTERED_WORKFLOWS:
                raise ValidationAppError(f"Unknown workflow action: {action}")
            if dest and dest not in screens:
                raise ValidationAppError(f"Destination screen missing: {dest}")
            if not action and not dest:
                raise ValidationAppError("Each option needs a workflow or destination screen")
            label = str(opt.get("label") or "")
            if "-" in label:
                raise ValidationAppError("Menu labels must not contain hyphens")

    async def update_draft(self, config_id: UUID, body: dict[str, Any]) -> UssdMenuConfig:
        row = await self.get_config(config_id)
        if row.status != UssdConfigStatus.DRAFT.value:
            raise ConflictError("Only draft configurations can be edited")
        if "name" in body and body["name"]:
            row.name = str(body["name"])[:128]
        if "welcome_text" in body and body["welcome_text"]:
            text = str(body["welcome_text"])
            if "-" in text:
                raise ValidationAppError("Welcome text must not contain hyphens")
            row.welcome_text = text[:320]
        if "definition" in body and isinstance(body["definition"], dict):
            self._validate_definition(body["definition"], row.root_screen_key)
            row.definition = body["definition"]
            flag_modified(row, "definition")
        for key in (
            "max_invalid_attempts",
            "session_ttl_seconds",
            "max_message_chars",
            "nav_back",
            "nav_home",
            "nav_repeat",
            "root_screen_key",
            "notes",
        ):
            if key in body and body[key] is not None:
                setattr(row, key, body[key])
        await self._audit("ussd.config_update", "ussd_menu_config", str(row.id), {"fields": list(body)})
        await self.session.flush()
        return row

    async def publish(self, config_id: UUID) -> UssdMenuConfig:
        row = await self.get_config(config_id)
        if row.status != UssdConfigStatus.DRAFT.value:
            raise ConflictError("Only draft configurations can be published")
        self._validate_definition(row.definition or {}, row.root_screen_key)
        current = await self.get_published()
        if current is not None and current.id != row.id:
            current.status = UssdConfigStatus.ARCHIVED.value
        row.status = UssdConfigStatus.PUBLISHED.value
        row.published_at = datetime.now(UTC)
        row.published_by = self.ctx.user_id
        await self._audit(
            "ussd.config_publish",
            "ussd_menu_config",
            str(row.id),
            {"version": row.version},
        )
        await self.session.flush()
        return row

    async def get_or_create_provider(self) -> UssdProviderSetting:
        row = await self.session.scalar(
            select(UssdProviderSetting).where(
                UssdProviderSetting.tenant_id == self.ctx.tenant_id
            )
        )
        if row is not None:
            return row
        row = UssdProviderSetting(
            tenant_id=self.ctx.tenant_id,
            provider_kind=UssdProviderKind.BIRDVIEW.value,
            service_code=get_settings().ussd_default_service_code,
            enabled=True,
            allowed_ips=[],
            protocol_options={},
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def update_provider(self, body: dict[str, Any]) -> UssdProviderSetting:
        row = await self.get_or_create_provider()
        if "provider_kind" in body and body["provider_kind"]:
            kind = str(body["provider_kind"])
            if kind not in {k.value for k in UssdProviderKind}:
                raise ValidationAppError("Unsupported provider kind")
            row.provider_kind = kind
        if "service_code" in body and body["service_code"]:
            row.service_code = str(body["service_code"])[:32]
        if "enabled" in body:
            row.enabled = bool(body["enabled"])
        if "auth_header_name" in body:
            row.auth_header_name = (str(body["auth_header_name"])[:64] or None)
        if "auth_secret" in body and body["auth_secret"]:
            # Store opaque; production should encrypt via app secrets helper.
            row.auth_secret_encrypted = str(body["auth_secret"])
        if "allowed_ips" in body and isinstance(body["allowed_ips"], list):
            row.allowed_ips = [str(x) for x in body["allowed_ips"][:50]]
        if "protocol_options" in body and isinstance(body["protocol_options"], dict):
            row.protocol_options = body["protocol_options"]
        row.updated_by = self.ctx.user_id
        await self._audit("ussd.provider_update", "ussd_provider_setting", str(row.id), {})
        await self.session.flush()
        return row

    @staticmethod
    def public_callback_url(path: str | None = None) -> str:
        """Absolute HTTPS URL Birdview should call (custom domain preferred)."""
        settings = get_settings()
        suffix = (path or "/api/v1/ussd/callback").strip() or "/api/v1/ussd/callback"
        if not suffix.startswith("/"):
            suffix = f"/{suffix}"
        api_prefix = (settings.api_prefix or "/api/v1").rstrip("/")
        if suffix == "/api/v1/ussd/callback" and api_prefix != "/api/v1":
            suffix = f"{api_prefix}/ussd/callback"

        app_url = (settings.email_app_url or "").strip().rstrip("/")
        # Production SPA is on quote.*; nginx proxies /api/v1 → Cloud Run API.
        if "quote.starserveinsuranceagency.com" in app_url:
            return f"https://quote.starserveinsuranceagency.com{suffix}"

        base = (
            (settings.birdview_callback_base_url or "").strip()
            or (settings.mpesa_callback_base_url or "").strip()
        ).rstrip("/")
        if base.startswith("https://") or base.startswith("http://"):
            return f"{base}{suffix}"
        return suffix

    def provider_public(self, row: UssdProviderSetting) -> dict[str, Any]:
        path = row.callback_path or "/api/v1/ussd/callback"
        return {
            "id": str(row.id),
            "provider_kind": row.provider_kind,
            "service_code": row.service_code,
            "enabled": row.enabled,
            "callback_path": path,
            "callback_url": self.public_callback_url(path),
            "auth_header_name": row.auth_header_name,
            "has_auth_secret": bool(row.auth_secret_encrypted),
            "allowed_ips": row.allowed_ips or [],
            "protocol_options": row.protocol_options or {},
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def config_public(self, row: UssdMenuConfig) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "version": row.version,
            "status": row.status,
            "name": row.name,
            "welcome_text": row.welcome_text,
            "root_screen_key": row.root_screen_key,
            "max_invalid_attempts": row.max_invalid_attempts,
            "session_ttl_seconds": row.session_ttl_seconds,
            "max_message_chars": row.max_message_chars,
            "nav_back": row.nav_back,
            "nav_home": row.nav_home,
            "nav_repeat": row.nav_repeat,
            "definition": row.definition,
            "published_at": row.published_at.isoformat() if row.published_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "notes": row.notes,
        }

    async def list_sessions(self, *, limit: int = 50, include_test: bool = True) -> list[dict]:
        rows = await self.session.scalars(
            select(UssdSession)
            .where(UssdSession.tenant_id == self.ctx.tenant_id)
            .order_by(UssdSession.created_at.desc())
            .limit(min(limit, 200))
        )
        out = []
        for row in rows:
            if not include_test and row.is_test:
                continue
            out.append(
                {
                    "id": str(row.id),
                    "status": row.status,
                    "msisdn_masked": row.msisdn_masked,
                    "workflow_action": row.workflow_action,
                    "workflow_step": row.workflow_step,
                    "config_version": row.config_version,
                    "is_test": row.is_test,
                    "provider_kind": row.provider_kind,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                    "termination_reason": row.termination_reason,
                    "last_message": row.last_message,
                }
            )
        return out

    async def get_session(self, session_id: UUID) -> dict[str, Any]:
        row = await self.session.get(UssdSession, session_id)
        if row is None or row.tenant_id != self.ctx.tenant_id:
            raise ResourceNotFoundError("USSD session not found")
        # Mask answers that look like identifiers.
        answers = dict(row.answers or {})
        for key in ("id_number", "msisdn"):
            if key in answers and answers[key]:
                val = str(answers[key])
                answers[key] = f"{val[:2]}***{val[-2:]}" if len(val) > 4 else "***"
        return {
            "id": str(row.id),
            "status": row.status,
            "msisdn_masked": row.msisdn_masked,
            "workflow_action": row.workflow_action,
            "workflow_step": row.workflow_step,
            "current_screen_key": row.current_screen_key,
            "config_version": row.config_version,
            "is_test": row.is_test,
            "history_depth": len(row.history or []),
            "answers": answers,
            "last_message": row.last_message,
            "last_response_type": row.last_response_type,
            "correlation_id": row.correlation_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "termination_reason": row.termination_reason,
        }

    async def _actor_names(self, user_ids: set[UUID]) -> dict[UUID, str]:
        if not user_ids:
            return {}
        rows = await self.session.scalars(select(User).where(User.id.in_(user_ids)))
        out: dict[UUID, str] = {}
        for user in rows:
            label = (user.full_name or user.email or "").strip()
            if label:
                out[user.id] = label
        return out

    async def _legacy_audit_events(self, *, cap: int) -> list[dict]:
        """Reconstruct audit rows from config/provider timestamps when the audit table is empty."""
        events: list[dict] = []
        configs = await self.session.scalars(
            select(UssdMenuConfig)
            .where(UssdMenuConfig.tenant_id == self.ctx.tenant_id)
            .order_by(UssdMenuConfig.version.desc())
        )
        for cfg in configs:
            if cfg.status == UssdConfigStatus.PUBLISHED.value and cfg.published_at:
                events.append(
                    {
                        "id": f"legacy-publish-{cfg.id}",
                        "action": "ussd.config_publish",
                        "resource": "ussd_menu_config",
                        "resource_id": str(cfg.id),
                        "actor_user_id": str(cfg.published_by) if cfg.published_by else None,
                        "actor_name": None,
                        "detail": {"version": cfg.version, "legacy": True},
                        "created_at": cfg.published_at.isoformat(),
                    }
                )
            elif cfg.status == UssdConfigStatus.DRAFT.value and cfg.created_at:
                events.append(
                    {
                        "id": f"legacy-draft-{cfg.id}",
                        "action": "ussd.config_create",
                        "resource": "ussd_menu_config",
                        "resource_id": str(cfg.id),
                        "actor_user_id": str(cfg.created_by) if cfg.created_by else None,
                        "actor_name": None,
                        "detail": {"version": cfg.version, "legacy": True},
                        "created_at": cfg.created_at.isoformat(),
                    }
                )
        provider = await self.session.scalar(
            select(UssdProviderSetting).where(
                UssdProviderSetting.tenant_id == self.ctx.tenant_id
            )
        )
        if provider and provider.updated_by and provider.updated_at:
            events.append(
                {
                    "id": f"legacy-provider-{provider.id}",
                    "action": "ussd.provider_update",
                    "resource": "ussd_provider_setting",
                    "resource_id": str(provider.id),
                    "actor_user_id": str(provider.updated_by),
                    "actor_name": None,
                    "detail": {"legacy": True},
                    "created_at": provider.updated_at.isoformat(),
                }
            )
        events.sort(key=lambda row: row.get("created_at") or "", reverse=True)
        return events[:cap]

    def _audit_public_row(self, row: UssdAdminAudit) -> dict:
        return {
            "id": str(row.id),
            "action": row.action,
            "resource": row.resource,
            "resource_id": row.resource_id,
            "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
            "actor_name": None,
            "detail": row.detail,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    async def list_audit(self, *, limit: int = 50) -> list[dict]:
        cap = min(limit, 200)
        rows = await self.session.scalars(
            select(UssdAdminAudit)
            .where(UssdAdminAudit.tenant_id == self.ctx.tenant_id)
            .order_by(UssdAdminAudit.created_at.desc())
            .limit(cap)
        )
        items = [self._audit_public_row(r) for r in rows]
        if not items:
            items = await self._legacy_audit_events(cap=cap)

        actor_ids: set[UUID] = set()
        for item in items:
            raw = item.get("actor_user_id")
            if not raw:
                continue
            try:
                actor_ids.add(UUID(str(raw)))
            except ValueError:
                continue
        names = await self._actor_names(actor_ids)
        for item in items:
            raw = item.get("actor_user_id")
            if not raw:
                continue
            try:
                uid = UUID(str(raw))
            except ValueError:
                continue
            item["actor_name"] = names.get(uid)
        return items
