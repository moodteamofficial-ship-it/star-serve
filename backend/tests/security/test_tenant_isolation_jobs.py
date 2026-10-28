"""Tenant isolation tests for JobService (in-memory SQLite-unfriendly; uses mocks).

Full DB isolation tests run in integration suite when Postgres is available.
"""

from uuid import uuid4

import pytest

from app.core.exceptions import ResourceNotFoundError, TenantAccessError
from app.core.security.context import SecurityContext
from app.modules.jobs.service import JobService


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def all(self):
        return self._value


class _FakeSession:
    def __init__(self, job=None):
        self.job = job
        self.added = []

    async def scalar(self, _stmt):
        return self.job

    async def scalars(self, _stmt):
        return _FakeResult([])

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_job_get_authorized_rejects_cross_tenant() -> None:
    tenant_a = uuid4()
    tenant_b = uuid4()
    ctx = SecurityContext(
        user_id=uuid4(),
        tenant_id=tenant_a,
        session_id=uuid4(),
        email="a@agency-a.local",
        role_id=uuid4(),
        role_code="test",
        permissions={"job:read"},
    )
    # Session returns None when tenant filter applied → not found (no leak)
    service = JobService(_FakeSession(job=None), ctx)
    with pytest.raises(ResourceNotFoundError):
        await service.get_authorized("JOB-other-tenant")


@pytest.mark.asyncio
async def test_job_service_requires_context_for_authorized() -> None:
    service = JobService(_FakeSession(), ctx=None)
    with pytest.raises(TenantAccessError):
        await service.get_authorized("JOB-123")
