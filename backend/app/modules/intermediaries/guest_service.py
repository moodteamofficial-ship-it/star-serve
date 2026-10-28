"""Self-service agent applications from the public welcome site.

Applicants never choose tenant, branch, or status: rows land as PENDING on the
guest session's agency and stay inert (QR lookups reject non-APPROVED codes)
until an admin approves them from the Intermediaries page.
"""

import secrets

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationAppError
from app.core.logging import get_logger
from app.core.security.branch_scope import first_active_tenant_branch_id
from app.core.security.guest_capabilities import GuestContext
from app.core.security.passwords import assert_password_strength
from app.core.security.request import client_ip
from app.core.validation.identity import normalize_id_number, normalize_kra_pin, normalize_phone
from app.modules.audit.service import AuditService
from app.modules.intermediaries.login import AgentLoginService
from app.modules.intermediaries.models import Intermediary
from app.modules.intermediaries.schemas import GuestAgentApplicationRequest
from app.modules.intermediaries.uniqueness import (
    agent_code_taken,
    duplicate_message,
    find_duplicate_fields,
)

logger = get_logger(__name__)

SELF_REGISTERED_NOTE = (
    "Self-registered from the public welcome page. Verify identity before approving."
)


class GuestAgentApplicationService:
    def __init__(self, session: AsyncSession, guest: GuestContext, request: Request) -> None:
        self.session = session
        self.guest = guest
        self.request = request
        self.audit = AuditService(session)

    async def _allocate_agent_code(self, preferred: str | None) -> str:
        if preferred:
            return preferred
        for _ in range(48):
            code = f"{secrets.randbelow(1_000_000):06d}"
            if not await agent_code_taken(self.session, code):
                return code
        raise ValidationAppError("Could not allocate an agent code. Please try again.")

    async def apply(self, body: GuestAgentApplicationRequest) -> dict:
        self.guest.require_active_tenant()
        received = {"status": "PENDING"}
        ip = client_ip(self.request)
        user_agent = (self.request.headers.get("user-agent") or "")[:255] or None

        if body.website and body.website.strip():
            logger.warning("guest_agent_apply_honeypot", extra={"ip": ip})
            return received

        identification = normalize_id_number(body.identification)
        phone = normalize_phone(body.phone)
        kra_pin = normalize_kra_pin(body.kra_pin)

        email = str(body.email).lower()
        clashes = await find_duplicate_fields(
            self.session,
            {
                "identification": identification,
                "phone": phone,
                "email": email,
                "agent_code": body.agent_code,
                "kra_pin": kra_pin,
            },
        )
        if clashes:
            await self.audit.record(
                action="intermediary.self_register",
                resource="intermediary",
                tenant_id=self.guest.tenant_id,
                result="DUPLICATE",
                ip_address=ip,
                user_agent=user_agent,
                metadata={"fields": clashes},
            )
            await self.session.commit()
            raise ConflictError(duplicate_message(clashes))

        logins = AgentLoginService(self.session, None)
        if body.password:
            assert_password_strength(body.password)
            await logins.assert_email_available(email)

        agent_code = await self._allocate_agent_code(body.agent_code)
        branch_id = await first_active_tenant_branch_id(self.session, self.guest.tenant_id)
        row = Intermediary(
            tenant_id=self.guest.tenant_id,
            branch_id=branch_id,
            created_by_user_id=None,
            name=body.name.strip(),
            email=email,
            phone=phone,
            identification=identification,
            agent_code=agent_code,
            kra_pin=kra_pin,
            status="PENDING",
            notes=SELF_REGISTERED_NOTE,
        )
        self.session.add(row)
        await self.session.flush()
        await self.audit.record(
            action="intermediary.self_register",
            resource="intermediary",
            resource_id=str(row.id),
            tenant_id=self.guest.tenant_id,
            ip_address=ip,
            user_agent=user_agent,
            metadata={"agent_code": agent_code, "source": "welcome"},
        )
        if body.password:
            await logins.provision(row, body.password)
        return received
