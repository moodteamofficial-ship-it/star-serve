"""Progressive login lockout — email + device, server-enforced, non-bypassable.

Schedule (per email+device and mirrored on email-global):
  1st lock: after 3 failures → 3 minutes
  2nd lock: after 2 failures → 10 minutes
  3rd lock: after 2 failures → 30 minutes
  then:     after 2 failures → 60, 120, 240, 480, 1440 minutes (cap)

Checks run before password verification. Rows are locked with FOR UPDATE.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.rls import set_rls_bypass
from app.core.exceptions.base import StarServeError
from app.modules.auth.lockout_models import LoginLockout

# First window needs 3 failures; every later window needs 2.
ATTEMPTS_BEFORE_FIRST_LOCK = 3
ATTEMPTS_BEFORE_LATER_LOCK = 2
# Email-global is a DoS lever against known addresses — keep it well above per-device.
EMAIL_GLOBAL_ATTEMPTS_FIRST = 15
EMAIL_GLOBAL_ATTEMPTS_LATER = 8

# Minutes for lockout_level 0, 1, 2, ... (cap at last)
LOCK_MINUTES_SCHEDULE: tuple[int, ...] = (3, 10, 30, 60, 120, 240, 480, 1440)

EMAIL_GLOBAL_DEVICE = "__email__"


class LoginLockedError(StarServeError):
    code = "LOGIN_LOCKED"
    http_status = 429
    message = "Too many failed sign-in attempts. Please try again later."


def normalize_email(email: str) -> str:
    return email.lower().strip()


def device_fingerprint(
    ip_address: str | None,
    user_agent: str | None,
    client_device_id: str | None = None,
) -> str:
    """Stable device key — client device id (if any) + IP + User-Agent (server-side)."""
    device = (client_device_id or "").strip()[:128]
    raw = (
        f"{device}|"
        f"{(ip_address or '').strip().lower()}|"
        f"{(user_agent or '').strip()[:512]}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def attempts_required_for_level(lockout_level: int, *, email_global: bool = False) -> int:
    if email_global:
        if lockout_level <= 0:
            return EMAIL_GLOBAL_ATTEMPTS_FIRST
        return EMAIL_GLOBAL_ATTEMPTS_LATER
    if lockout_level <= 0:
        return ATTEMPTS_BEFORE_FIRST_LOCK
    return ATTEMPTS_BEFORE_LATER_LOCK


def lock_minutes_for_level(lockout_level: int) -> int:
    """Duration applied when escalating from this level (0 → first lock = 3 min)."""
    idx = max(0, lockout_level)
    if idx >= len(LOCK_MINUTES_SCHEDULE):
        return LOCK_MINUTES_SCHEDULE[-1]
    return LOCK_MINUTES_SCHEDULE[idx]


def remaining_lock_seconds(locked_until: datetime | None, *, now: datetime | None = None) -> int:
    if locked_until is None:
        return 0
    current = now or datetime.now(UTC)
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=UTC)
    delta = locked_until - current
    return max(0, int(delta.total_seconds()))


class LoginLockoutService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def assert_not_locked(
        self,
        *,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
        client_device_id: str | None = None,
    ) -> None:
        await set_rls_bypass(self.session, True)
        email_n = normalize_email(email)
        device = device_fingerprint(ip_address, user_agent, client_device_id)
        now = datetime.now(UTC)

        rows = await self._get_or_create_pair_for_update(email_n, device)
        for row in rows:
            if row.locked_until and row.locked_until > now:
                secs = remaining_lock_seconds(row.locked_until, now=now)
                mins = max(1, (secs + 59) // 60)
                raise LoginLockedError(
                    f"Too many failed sign-in attempts. Try again in about {mins} minute"
                    f"{'s' if mins != 1 else ''}.",
                    details=[
                        {
                            "locked_until": row.locked_until.isoformat(),
                            "retry_after_seconds": secs,
                            "lockout_level": row.lockout_level,
                        }
                    ],
                )

    async def record_failure(
        self,
        *,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
        client_device_id: str | None = None,
    ) -> LoginLockout:
        """Increment device + email-global counters; may engage a lock on both."""
        await set_rls_bypass(self.session, True)
        email_n = normalize_email(email)
        device = device_fingerprint(ip_address, user_agent, client_device_id)
        now = datetime.now(UTC)

        pair = await self._apply_failure(email_n, device, now)
        global_row = await self._apply_failure(email_n, EMAIL_GLOBAL_DEVICE, now)
        # Prefer the stricter active lock for caller sync
        if global_row.locked_until and (
            pair.locked_until is None or global_row.locked_until > pair.locked_until
        ):
            return global_row
        return pair

    async def clear_on_success(
        self,
        *,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
        client_device_id: str | None = None,
    ) -> None:
        """Clear only after verified successful login — never from the client."""
        email_n = normalize_email(email)
        device = device_fingerprint(ip_address, user_agent, client_device_id)
        now = datetime.now(UTC)

        await self.session.execute(
            update(LoginLockout)
            .where(
                LoginLockout.email == email_n,
                LoginLockout.device_fingerprint.in_((device, EMAIL_GLOBAL_DEVICE)),
            )
            .values(
                failed_attempts=0,
                lockout_level=0,
                locked_until=None,
                last_success_at=now,
                updated_at=now,
            )
        )

    async def _apply_failure(self, email: str, device_fp: str, now: datetime) -> LoginLockout:
        row = await self._get_or_create_for_update(email, device_fp)

        # Already locked — do not reset the clock by re-failing
        if row.locked_until and row.locked_until > now:
            row.last_attempt_at = now
            row.updated_at = now
            return row

        # Lock expired: keep escalation level, reopen attempt window
        if row.locked_until and row.locked_until <= now:
            row.locked_until = None
            row.failed_attempts = 0

        row.failed_attempts += 1
        row.last_attempt_at = now
        row.updated_at = now

        needed = attempts_required_for_level(
            row.lockout_level, email_global=(device_fp == EMAIL_GLOBAL_DEVICE)
        )
        if row.failed_attempts >= needed:
            minutes = lock_minutes_for_level(row.lockout_level)
            row.locked_until = now + timedelta(minutes=minutes)
            row.lockout_level += 1
            row.failed_attempts = 0
            row.last_lock_at = now

        return row

    async def _get_or_create_pair_for_update(
        self, email: str, device_fp: str
    ) -> list[LoginLockout]:
        """Lock device + email-global rows in one query (create missing)."""
        fingerprints = (device_fp, EMAIL_GLOBAL_DEVICE)
        stmt = (
            select(LoginLockout)
            .where(
                LoginLockout.email == email,
                LoginLockout.device_fingerprint.in_(fingerprints),
            )
            .with_for_update()
        )
        existing = {r.device_fingerprint: r for r in (await self.session.scalars(stmt)).all()}
        missing = [fp for fp in fingerprints if fp not in existing]
        for fp in missing:
            await self.session.execute(
                insert(LoginLockout)
                .values(
                    id=uuid4(),
                    email=email,
                    device_fingerprint=fp,
                    failed_attempts=0,
                    lockout_level=0,
                )
                .on_conflict_do_nothing(
                    constraint="uq_login_lockouts_email_device",
                )
            )
        if missing:
            existing = {r.device_fingerprint: r for r in (await self.session.scalars(stmt)).all()}
        out = [existing[fp] for fp in fingerprints if fp in existing]
        if len(out) != 2:
            raise RuntimeError("Failed to create login_lockouts pair")
        return out

    async def _get_or_create_for_update(self, email: str, device_fp: str) -> LoginLockout:
        stmt = (
            select(LoginLockout)
            .where(
                LoginLockout.email == email,
                LoginLockout.device_fingerprint == device_fp,
            )
            .with_for_update()
        )
        row = await self.session.scalar(stmt)
        if row is not None:
            return row

        await self.session.execute(
            insert(LoginLockout)
            .values(
                id=uuid4(),
                email=email,
                device_fingerprint=device_fp,
                failed_attempts=0,
                lockout_level=0,
            )
            .on_conflict_do_nothing(
                constraint="uq_login_lockouts_email_device",
            )
        )
        row = await self.session.scalar(stmt)
        if row is None:
            raise RuntimeError("Failed to create login_lockouts row")
        return row
