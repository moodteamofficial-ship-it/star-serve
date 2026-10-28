"""Authentication service — login, refresh rotation, logout, lockout.

Primary role (users.role_id) is validated against the roles + user_roles tables
on every sign-in and refresh. Sessions snapshot role_id + app_env.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database.enums import SessionStatus, TenantStatus, UserStatus
from app.core.database.rls import set_auth_write_gate, set_rls_bypass, set_rls_context
from app.core.exceptions import AuthenticationError, SystemUnavailableError, TenantSuspendedError
from app.core.security.passwords import hash_password, is_forbidden_password, needs_rehash, verify_password

# Same Argon2 cost as a real user so unknown emails do not short-circuit.
_DUMMY_PASSWORD_HASH = hash_password(
    "timing-pad-never-a-real-password!!", enforce_strength=False
)
from app.core.security.tokens import create_access_token, generate_refresh_token
from app.modules.audit.service import AuditService
from app.modules.auth.lockout import LoginLockedError, LoginLockoutService, remaining_lock_seconds
from app.modules.roles.service import ResolvedRole, resolve_user_role
from app.modules.system_config.service import SystemConfigService
from app.modules.tenants.models import Tenant
from app.modules.users.models import Session, User


def _hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)
        self.settings = get_settings()
        self.lockouts = LoginLockoutService(session)

    async def _persist_lockout_state(self) -> None:
        """Commit lockout / status writes even when login ultimately fails.

        Without this, get_db() rolls back on AuthenticationError and counters never stick.
        """
        await self.session.flush()
        await self.session.commit()
        await set_rls_bypass(self.session, True)

    async def register_user(
        self,
        *,
        tenant_id: UUID,
        email: str,
        password: str,
        full_name: str,
        phone: str | None = None,
        is_platform_admin: bool = False,
        status: str = UserStatus.ACTIVE.value,
        role_id: UUID | None = None,
    ) -> User:
        await set_rls_bypass(self.session, True)
        await set_auth_write_gate(self.session, allow_auth_write=True, allow_status_write=True)
        user = User(
            tenant_id=tenant_id,
            email=email.lower().strip(),
            phone=phone,
            full_name=full_name,
            password_hash=hash_password(password),
            status=status,
            is_platform_admin=is_platform_admin,
            role_id=role_id,
            email_verified_at=datetime.now(UTC) if status == UserStatus.ACTIVE.value else None,
        )
        self.session.add(user)
        await self.session.flush()
        await set_auth_write_gate(self.session, allow_auth_write=False, allow_status_write=False)
        return user

    async def assign_primary_role(
        self,
        *,
        user: User,
        role_id: UUID,
        tenant_id: UUID,
    ) -> None:
        """Assign role in user_roles and set users.role_id (gated writes)."""
        from app.modules.roles.models import UserRole

        await set_rls_bypass(self.session, True)
        await set_auth_write_gate(self.session, allow_auth_write=True)
        existing = await self.session.scalar(
            select(UserRole).where(
                UserRole.user_id == user.id,
                UserRole.role_id == role_id,
                UserRole.deleted_at.is_(None),
            )
        )
        if existing is None:
            self.session.add(
                UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role_id)
            )
        user.role_id = role_id
        await self.session.flush()
        await set_auth_write_gate(self.session, allow_auth_write=False)

    async def authenticate(
        self,
        *,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        client_device_id: str | None = None,
    ) -> tuple[User, Tenant, str, str, Session, ResolvedRole]:
        invalid = AuthenticationError("Invalid email or password")
        email_n = email.lower().strip()
        now = datetime.now(UTC)

        try:
            await self.lockouts.assert_not_locked(
                email=email_n,
                ip_address=ip_address,
                user_agent=user_agent,
                client_device_id=client_device_id,
            )
        except LoginLockedError:
            await self._persist_lockout_state()
            # Lock is checked before the password. Do not disguise it as a
            # credential miss — that makes valid users think the DB rejected them.
            raise

        # assert_not_locked already enabled rls_bypass for this transaction
        user = (
            await self.session.scalars(
                select(User)
                .where(
                    func.lower(User.email) == email_n,
                    User.deleted_at.is_(None),
                )
                .limit(1)
            )
        ).first()
        if user is None:
            verify_password(password, _DUMMY_PASSWORD_HASH)
            await self.lockouts.record_failure(
                email=email_n,
                ip_address=ip_address,
                user_agent=user_agent,
                client_device_id=client_device_id,
            )
            await self.audit.record(
                action="auth.login_failed",
                resource="user",
                result="FAILURE",
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"reason": "unknown_user"},
            )
            await self._persist_lockout_state()
            raise invalid

        tenant = await self.session.get(Tenant, user.tenant_id)
        if tenant is None:
            verify_password(password, _DUMMY_PASSWORD_HASH)
            await self.lockouts.record_failure(
                email=email_n,
                ip_address=ip_address,
                user_agent=user_agent,
                client_device_id=client_device_id,
            )
            await self._persist_lockout_state()
            raise invalid
        if user.status == UserStatus.DELETED.value or user.deleted_at is not None:
            await self.lockouts.record_failure(
                email=email_n,
                ip_address=ip_address,
                user_agent=user_agent,
                client_device_id=client_device_id,
            )
            await self._persist_lockout_state()
            raise AuthenticationError("Invalid email or password")

        if user.locked_until and user.locked_until > now:
            await self.audit.record(
                action="auth.login_locked",
                resource="user",
                resource_id=str(user.id),
                tenant_id=user.tenant_id,
                user_id=user.id,
                result="FAILURE",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            await self._persist_lockout_state()
            secs = remaining_lock_seconds(user.locked_until, now=now)
            mins = max(1, (secs + 59) // 60)
            raise LoginLockedError(
                f"Too many failed sign-in attempts. Try again in about {mins} minute"
                f"{'s' if mins != 1 else ''}.",
                details=[
                    {
                        "locked_until": user.locked_until.isoformat(),
                        "retry_after_seconds": secs,
                    }
                ],
            )

        if user.status == UserStatus.DISABLED.value:
            raise AuthenticationError("Invalid email or password")

        if not verify_password(password, user.password_hash):
            pair = await self.lockouts.record_failure(
                email=email_n,
                ip_address=ip_address,
                user_agent=user_agent,
                client_device_id=client_device_id,
            )
            # Keep status write gate open until after flush/commit (SET LOCAL)
            await set_auth_write_gate(self.session, allow_status_write=True)
            user.failed_login_attempts = pair.failed_attempts
            if pair.locked_until and pair.locked_until > now:
                user.locked_until = pair.locked_until
                # locked_until enforces the lockout; a PENDING user must stay PENDING so
                # a successful login after the lock cannot promote it to ACTIVE.
                if user.status != UserStatus.PENDING.value:
                    user.status = UserStatus.LOCKED.value
                await self.revoke_all_sessions(user.id)
            await self.audit.record(
                action="auth.login_failed",
                resource="user",
                resource_id=str(user.id),
                tenant_id=user.tenant_id,
                user_id=user.id,
                result="FAILURE",
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={
                    "reason": "bad_password",
                    "lockout_level": pair.lockout_level,
                    "failed_attempts": pair.failed_attempts,
                    "locked": bool(pair.locked_until and pair.locked_until > now),
                },
            )
            await self._persist_lockout_state()
            if pair.locked_until and pair.locked_until > now:
                secs = remaining_lock_seconds(pair.locked_until, now=now)
                mins = max(1, (secs + 59) // 60)
                raise LoginLockedError(
                    f"Too many failed sign-in attempts. Try again in about {mins} minute"
                    f"{'s' if mins != 1 else ''}.",
                    details=[
                        {
                            "locked_until": pair.locked_until.isoformat(),
                            "retry_after_seconds": secs,
                            "lockout_level": pair.lockout_level,
                        }
                    ],
                )
            raise invalid

        if user.status == UserStatus.PENDING.value:
            from app.core.dependencies.auth import PENDING_APPROVAL_MESSAGE

            raise AuthenticationError(PENDING_APPROVAL_MESSAGE)

        # Hash already matched. A denylist must not impersonate a wrong password
        # for accounts created before the policy. New secrets are still rejected
        # at register / change-password.
        if is_forbidden_password(password):
            await self.audit.record(
                action="auth.login",
                resource="user",
                resource_id=str(user.id),
                tenant_id=user.tenant_id,
                user_id=user.id,
                result="SUCCESS",
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"reason": "legacy_weak_password"},
            )

        if tenant.status in {
            TenantStatus.SUSPENDED.value,
            TenantStatus.DISABLED.value,
            TenantStatus.ARCHIVED.value,
        }:
            raise TenantSuspendedError()

        # Master switch from DB — only platform admins may sign in when off.
        operational = await SystemConfigService(self.session).get_operational()
        if not operational.enabled and not user.is_platform_admin:
            raise SystemUnavailableError(
                operational.reason or "The platform is temporarily switched off"
            )

        # Keep bypass + status gate; validate primary role once (returned to router)
        await set_auth_write_gate(self.session, allow_status_write=True)
        resolved = await resolve_user_role(self.session, user=user)

        if needs_rehash(user.password_hash):
            await set_auth_write_gate(self.session, allow_auth_write=True, allow_status_write=True)
            user.password_hash = hash_password(password, enforce_strength=False)
            await set_auth_write_gate(self.session, allow_auth_write=False, allow_status_write=True)

        await self.lockouts.clear_on_success(
            email=email_n,
            ip_address=ip_address,
            user_agent=user_agent,
            client_device_id=client_device_id,
        )
        # Status/locked_until writes require the gate open through flush+commit
        await set_auth_write_gate(self.session, allow_status_write=True)
        user.failed_login_attempts = 0
        user.locked_until = None
        if user.status == UserStatus.LOCKED.value:
            user.status = UserStatus.ACTIVE.value
        user.last_login_at = datetime.now(UTC)
        user.preferred_app_env = self.settings.app_env
        await self.session.flush()

        access, refresh, session = await self._issue_session(
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            resolved=resolved,
            tenant=tenant,
        )

        await self.audit.record(
            action="auth.login",
            resource="session",
            resource_id=str(session.id),
            tenant_id=user.tenant_id,
            user_id=user.id,
            result="SUCCESS",
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={
                "role_id": str(user.role_id),
                "app_env": self.settings.app_env,
                "superseded_sessions": (session.meta or {}).get("superseded_sessions", 0),
            },
        )
        await self._notify_sign_in(
            user=user,
            tenant=tenant,
            session=session,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return user, tenant, access, refresh, session, resolved

    async def refresh(
        self,
        *,
        refresh_token: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[User, str, str, Session, ResolvedRole]:
        await set_rls_bypass(self.session, True)
        token_hash = _hash_refresh(refresh_token)
        stmt = select(Session).where(Session.refresh_token_hash == token_hash)
        session = await self.session.scalar(stmt)
        if session is None:
            raise AuthenticationError("Invalid refresh token")

        if session.revoked_at is not None:
            await self._revoke_family(session.family_id)
            await self.audit.record(
                action="auth.refresh_reuse_detected",
                resource="session",
                resource_id=str(session.id),
                tenant_id=session.tenant_id,
                user_id=session.user_id,
                result="FAILURE",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise AuthenticationError("Refresh token reuse detected")

        if session.expires_at < datetime.now(UTC):
            raise AuthenticationError("Refresh token expired")

        if session.app_env and session.app_env != self.settings.app_env:
            raise AuthenticationError("Session environment mismatch — please sign in again")

        user = await self.session.get(User, session.user_id)
        if user is None or user.status in {
            UserStatus.DISABLED.value,
            UserStatus.DELETED.value,
            UserStatus.LOCKED.value,
            UserStatus.PENDING.value,
        }:
            if user is not None and user.status == UserStatus.LOCKED.value:
                await self.revoke_all_sessions(user.id)
            raise AuthenticationError("Invalid refresh token")

        await set_rls_context(
            self.session,
            tenant_id=user.tenant_id,
            is_platform_admin=user.is_platform_admin,
            user_id=user.id,
            role_id=user.role_id,
            rls_bypass=True,
        )
        # Serialize with a concurrent login so a newer device wins cleanly.
        await self._lock_user_for_sessions(user.id)
        await self.session.refresh(session)
        if session.revoked_at is not None or session.status != SessionStatus.ACTIVE.value:
            raise AuthenticationError("Session is no longer valid")

        resolved = await resolve_user_role(self.session, user=user)
        if session.role_id != resolved.role_id:
            raise AuthenticationError("Session role is no longer valid — please sign in again")

        access, new_refresh, new_session = await self._issue_session(
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            family_id=session.family_id,
            resolved=resolved,
        )
        await self.audit.record(
            action="auth.refresh",
            resource="session",
            resource_id=str(new_session.id),
            tenant_id=user.tenant_id,
            user_id=user.id,
            result="SUCCESS",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return user, access, new_refresh, new_session, resolved

    async def set_preferred_app_env(self, *, user: User, app_env: str) -> User:
        """Persist the user's target data plane (frontend env switcher)."""
        user.preferred_app_env = app_env
        await self.session.flush()
        await self.audit.record(
            action="auth.preferred_app_env",
            resource="user",
            resource_id=str(user.id),
            tenant_id=user.tenant_id,
            user_id=user.id,
            result="SUCCESS",
            metadata={"preferred_app_env": app_env},
        )
        return user

    async def logout(
        self,
        *,
        refresh_token: str | None,
        access_token: str | None = None,
        user_id: UUID | None = None,
    ) -> None:
        """Revoke the server session. Cookies are not the source of truth.

        A missing refresh cookie must not leave the session ACTIVE if the
        access token (even an expired one) still identifies it.
        """
        await set_rls_bypass(self.session, True)
        seen: set[UUID] = set()

        if refresh_token:
            token_hash = _hash_refresh(refresh_token)
            session = await self.session.scalar(
                select(Session).where(Session.refresh_token_hash == token_hash)
            )
            if session is not None:
                await self._revoke_session_row(session)
                seen.add(session.id)

        if access_token:
            from app.core.security.tokens import decode_access_token

            try:
                payload = decode_access_token(access_token, verify_exp=False)
                sid = UUID(str(payload["sid"]))
            except (AuthenticationError, KeyError, ValueError, TypeError):
                sid = None
            if sid is not None and sid not in seen:
                session = await self.session.get(Session, sid)
                if session is not None:
                    await self._revoke_session_row(session)
                    seen.add(session.id)
                    user_id = user_id or session.user_id

        if not seen and user_id:
            await self.revoke_all_sessions(user_id)

    async def _revoke_session_row(self, session: Session) -> None:
        if session.revoked_at is not None or session.status != SessionStatus.ACTIVE.value:
            return
        await set_auth_write_gate(self.session, allow_status_write=True)
        now = datetime.now(UTC)
        session.revoked_at = now
        session.status = SessionStatus.REVOKED.value
        await self.audit.record(
            action="auth.logout",
            resource="session",
            resource_id=str(session.id),
            tenant_id=session.tenant_id,
            user_id=session.user_id,
            result="SUCCESS",
        )

    async def revoke_all_sessions(self, user_id: UUID, *, deleted_by: UUID | None = None) -> None:
        """Soft-revoke sessions — never DELETE rows."""
        await set_rls_bypass(self.session, True)
        await set_auth_write_gate(self.session, allow_status_write=True)
        now = datetime.now(UTC)
        await self.session.execute(
            update(Session)
            .where(
                Session.user_id == user_id,
                Session.revoked_at.is_(None),
                Session.deleted_at.is_(None),
            )
            .values(
                revoked_at=now,
                status=SessionStatus.REVOKED.value,
                deleted_at=now,
                deleted_by=deleted_by or user_id,
            )
        )
        await set_auth_write_gate(self.session, allow_status_write=False)

    async def revoke_sessions_for_role(
        self, role_id: UUID, *, deleted_by: UUID | None = None
    ) -> int:
        """End sessions when a role itself is disabled — not on permission edits."""
        await set_rls_bypass(self.session, True)
        await set_auth_write_gate(self.session, allow_status_write=True)
        now = datetime.now(UTC)
        result = await self.session.execute(
            update(Session)
            .where(
                Session.role_id == role_id,
                Session.revoked_at.is_(None),
                Session.deleted_at.is_(None),
            )
            .values(
                revoked_at=now,
                status=SessionStatus.REVOKED.value,
                deleted_at=now,
                deleted_by=deleted_by,
            )
        )
        await set_auth_write_gate(self.session, allow_status_write=False)
        return int(result.rowcount or 0)

    async def soft_delete_user(
        self,
        *,
        user: User,
        deleted_by: UUID,
        reason: str | None = None,
    ) -> None:
        """Mark account deleted — never hard-delete the row."""
        await set_rls_bypass(self.session, True)
        await set_auth_write_gate(self.session, allow_auth_write=True, allow_status_write=True)
        now = datetime.now(UTC)
        user.status = UserStatus.DELETED.value
        user.deleted_at = now
        user.deleted_by = deleted_by
        await self.revoke_all_sessions(user.id, deleted_by=deleted_by)
        await set_auth_write_gate(self.session, allow_auth_write=False, allow_status_write=False)
        await self.audit.record(
            action="user.soft_delete",
            resource="user",
            resource_id=str(user.id),
            tenant_id=user.tenant_id,
            user_id=deleted_by,
            result="SUCCESS",
            metadata={"reason": reason},
        )

    async def _lock_user_for_sessions(self, user_id: UUID) -> None:
        """Serialize login/refresh so two devices cannot both keep an ACTIVE row."""
        await set_rls_bypass(self.session, True)
        await self.session.execute(select(User.id).where(User.id == user_id).with_for_update())

    async def _revoke_active_sessions(self, user_id: UUID) -> int:
        """Soft-revoke every live session for the user. Rows are kept for audit."""
        await set_rls_bypass(self.session, True)
        await set_auth_write_gate(self.session, allow_status_write=True)
        now = datetime.now(UTC)
        result = await self.session.execute(
            update(Session)
            .where(
                Session.user_id == user_id,
                Session.deleted_at.is_(None),
                Session.revoked_at.is_(None),
            )
            .values(
                revoked_at=now,
                status=SessionStatus.REVOKED.value,
                updated_at=now,
            )
        )
        return int(result.rowcount or 0)

    async def _issue_session(
        self,
        *,
        user: User,
        ip_address: str | None,
        user_agent: str | None,
        family_id: UUID | None = None,
        resolved: ResolvedRole | None = None,
        tenant: Tenant | None = None,
        branch_ids: set[UUID] | None = None,
    ) -> tuple[str, str, Session]:
        if user.role_id is None:
            raise AuthenticationError("Account has no role assigned")
        if resolved is None:
            resolved = await resolve_user_role(self.session, user=user)
        if tenant is None:
            tenant = await self.session.get(Tenant, user.tenant_id)
        if tenant is None:
            raise AuthenticationError("Organization not found")

        if branch_ids is None:
            from app.modules.roles.service import load_user_branch_ids

            branch_ids = await load_user_branch_ids(self.session, user_id=user.id)

        await self._lock_user_for_sessions(user.id)
        superseded = await self._revoke_active_sessions(user.id)

        refresh = generate_refresh_token()
        session = Session(
            tenant_id=user.tenant_id,
            user_id=user.id,
            role_id=user.role_id,
            app_env=self.settings.app_env,
            status=SessionStatus.ACTIVE.value,
            refresh_token_hash=_hash_refresh(refresh),
            family_id=family_id or uuid4(),
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=datetime.now(UTC)
            + timedelta(days=self.settings.jwt_refresh_token_days),
            meta={
                "role_id": str(user.role_id),
                "app_env": self.settings.app_env,
                "superseded_sessions": superseded,
            },
        )
        self.session.add(session)
        await self.session.flush()
        access = create_access_token(
            user_id=str(user.id),
            session_id=str(session.id),
            tenant_id=str(user.tenant_id),
            role_id=str(resolved.role_id),
            role_code=resolved.code,
            email=user.email,
            is_platform_admin=user.is_platform_admin,
            tenant_status=tenant.status,
            branch_ids=[str(b) for b in (branch_ids or ())],
        )
        return access, refresh, session

    async def _revoke_family(self, family_id: UUID) -> None:
        await set_rls_bypass(self.session, True)
        now = datetime.now(UTC)
        await self.session.execute(
            update(Session)
            .where(Session.family_id == family_id, Session.revoked_at.is_(None))
            .values(
                revoked_at=now,
                reused_at=now,
                status=SessionStatus.REVOKED.value,
            )
        )

    async def change_password(
        self, *, user: User, current_password: str, new_password: str
    ) -> None:
        if not verify_password(current_password, user.password_hash):
            raise AuthenticationError("Invalid current password")
        await set_rls_bypass(self.session, True)
        await set_auth_write_gate(self.session, allow_auth_write=True)
        user.password_hash = hash_password(new_password)
        await set_auth_write_gate(self.session, allow_auth_write=False)
        await self.revoke_all_sessions(user.id)
        await self.audit.record(
            action="auth.password_changed",
            resource="user",
            resource_id=str(user.id),
            tenant_id=user.tenant_id,
            user_id=user.id,
            result="SUCCESS",
        )

    async def _notify_sign_in(
        self,
        *,
        user: User,
        tenant: Tenant,
        session: Session,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        from app.modules.notifications.account_mail import (
            device_label,
            notify_account_email,
            sign_in_stamp,
        )
        from app.modules.notifications.enums import NotificationTemplate

        await notify_account_email(
            self.session,
            user,
            template=NotificationTemplate.ACCOUNT_SIGNED_IN.value,
            session_id=session.id,
            tenant_status=tenant.status,
            context={
                "sign_in_at": sign_in_stamp(),
                "ip_address": (ip_address or "").strip() or "Unknown",
                "device": device_label(user_agent),
            },
        )
