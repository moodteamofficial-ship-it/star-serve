"""Idempotency key helper for critical mutations."""

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, IdempotencyConflictError
from app.core.jsoning import json_ready
from app.modules.jobs.models import IdempotencyKey


class IdempotencyService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def hash_request(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def begin(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID | None,
        key: str,
        operation: str,
        request_hash: str,
    ) -> IdempotencyKey | dict[str, Any]:
        existing = await self.session.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.tenant_id == tenant_id,
                IdempotencyKey.idempotency_key == key,
                IdempotencyKey.operation == operation,
            )
        )
        if existing:
            if existing.request_hash != request_hash:
                raise ConflictError("Idempotency key reused with a different payload")
            if existing.status == "COMPLETED" and existing.response_body is not None:
                return existing.response_body
            if existing.status == "PENDING":
                raise IdempotencyConflictError()
            if existing.status == "FAILED" and existing.request_hash == request_hash:
                existing.status = "PENDING"
                existing.response_body = None
                await self.session.flush()
                return existing
            return existing.response_body or {}

        record = IdempotencyKey(
            tenant_id=tenant_id,
            user_id=user_id,
            idempotency_key=key,
            operation=operation,
            request_hash=request_hash,
            status="PENDING",
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def complete(
        self,
        record: IdempotencyKey,
        *,
        response_body: dict[str, Any],
        job_id: str | None = None,
    ) -> None:
        record.status = "COMPLETED"
        record.response_body = json_ready(response_body)
        record.job_id = job_id
        await self.session.flush()

    async def fail(self, record: IdempotencyKey) -> None:
        record.status = "FAILED"
        await self.session.flush()
