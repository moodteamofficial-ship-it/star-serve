"""Workflow handler contract for registered USSD actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ussd.enums import UssdResponseType
from app.modules.ussd.models import UssdSession


@dataclass(slots=True)
class WorkflowResult:
    message: str
    response_type: str = UssdResponseType.CONTINUE.value
    step: str | None = None
    answers_patch: dict[str, Any] = field(default_factory=dict)
    event_type: str | None = None
    outcome: str | None = None
    error_category: str | None = None
    clear_workflow: bool = False


class WorkflowHandler(Protocol):
    action: str

    async def start(self, session: AsyncSession, ussd: UssdSession) -> WorkflowResult: ...

    async def handle(
        self, session: AsyncSession, ussd: UssdSession, text: str
    ) -> WorkflowResult: ...
