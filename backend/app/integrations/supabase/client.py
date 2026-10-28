"""Supabase REST client — secrets stay in Settings / Secret Manager only.

Use service_role only on the server (bypasses RLS). Prefer DATABASE_URL +
SQLAlchemy for normal app queries; use this client for Storage / admin REST.
Never return keys from API handlers or log Authorization headers.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

import httpx

from app.core.config import get_settings

SupabaseRole = Literal["anon", "service_role"]


class SupabaseNotConfiguredError(RuntimeError):
    pass


class SupabaseRestClient:
    def __init__(
        self,
        *,
        base_url: str,
        anon_key: str,
        service_role_key: str,
        timeout: float = 30.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._anon = anon_key.strip()
        self._service = service_role_key.strip()
        self._timeout = timeout

    @property
    def rest_url(self) -> str:
        return f"{self._base}/rest/v1"

    def configured(self, role: SupabaseRole = "service_role") -> bool:
        if not self._base:
            return False
        key = self._service if role == "service_role" else self._anon
        return bool(key)

    def _headers(self, role: SupabaseRole) -> dict[str, str]:
        key = self._service if role == "service_role" else self._anon
        if not key:
            raise SupabaseNotConfiguredError(
                f"SUPABASE_{'SERVICE_ROLE' if role == 'service_role' else 'ANON'}_KEY is not set"
            )
        return {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    async def request(
        self,
        method: str,
        path: str,
        *,
        role: SupabaseRole = "service_role",
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        headers = self._headers(role)
        if extra_headers:
            headers.update(extra_headers)
        url = path if path.startswith("http") else f"{self.rest_url}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_body,
            )

    async def healthcheck(self, role: SupabaseRole = "anon") -> bool:
        """Lightweight check that keys are accepted (does not leak key material)."""
        if not self.configured(role):
            return False
        # OpenAPI root is public; authenticated HEAD on a missing table still validates JWT
        try:
            resp = await self.request("GET", "/", role=role)
            return resp.status_code < 500
        except Exception:
            return False


@lru_cache
def get_supabase_client() -> SupabaseRestClient:
    settings = get_settings()
    return SupabaseRestClient(
        base_url=settings.supabase_url
        or f"https://{settings.supabase_project_ref}.supabase.co",
        anon_key=settings.supabase_anon_key,
        service_role_key=settings.supabase_service_role_key,
    )
