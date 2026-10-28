"""Provider adapter interface — application workflows stay provider-agnostic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from starlette.requests import Request
from starlette.responses import Response


@dataclass(slots=True)
class ProviderCallback:
    provider_kind: str
    service_code: str
    session_id: str
    msisdn: str
    text: str | None
    network_code: str | None = None
    raw: dict[str, Any] | None = None
    idempotency_key: str | None = None


class UssdProviderAdapter(Protocol):
    kind: str

    async def authenticate(self, request: Request, settings: Any) -> None: ...

    async def parse(self, request: Request) -> ProviderCallback: ...

    def render(self, *, text: str, response_type: str) -> Response: ...
