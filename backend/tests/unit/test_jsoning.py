"""JSONB-safe encoding for Decimal / UUID / datetime payloads."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import json
import pytest

from app.core.idempotency.service import IdempotencyService
from app.core.jsoning import dumps_jsonb, json_ready


def test_json_ready_encodes_decimal_uuid_and_dates() -> None:
    payload = {
        "gross_premium": Decimal("1913.00"),
        "levy": Decimal("4.50"),
        "id": UUID("bd068e11-a3ac-42c5-ab29-4ef7f4bd9eaa"),
        "cover_start_date": date(2026, 9, 14),
        "created_at": datetime(2026, 9, 14, 17, 0, 8, tzinfo=UTC),
        "nested": {"amount": Decimal("12.50")},
        "flags": (True, Decimal("0")),
    }
    ready = json_ready(payload)
    dumped = json.dumps(ready)
    loaded = json.loads(dumped)
    assert loaded["gross_premium"] == 1913
    assert loaded["levy"] == 4.5
    assert loaded["id"] == "bd068e11-a3ac-42c5-ab29-4ef7f4bd9eaa"
    assert loaded["cover_start_date"] == "2026-09-14"
    assert loaded["created_at"].startswith("2026-09-14T17:00:08")
    assert loaded["nested"]["amount"] == 12.5
    assert loaded["flags"] == [True, 0]


def test_dumps_jsonb_serializes_guest_submit_shape() -> None:
    body = {
        "job_id": "JOB-01M2G3FEX4K8MZ5B518NGG7JVY",
        "premium": {"basic_premium": Decimal("1900.0"), "stamp_duty": Decimal("40.00")},
        "proposal": {"gross_premium": Decimal("1913.00")},
    }
    dumped = dumps_jsonb(body)
    loaded = json.loads(dumped)
    assert loaded["premium"]["basic_premium"] == 1900
    assert loaded["proposal"]["gross_premium"] == 1913


@pytest.mark.asyncio
async def test_idempotency_complete_accepts_decimal_response_body() -> None:
    session = AsyncMock()
    record = MagicMock()
    await IdempotencyService(session).complete(
        record,
        response_body={
            "premium": {"basic_premium": Decimal("1900.0")},
            "proposal": {"gross_premium": Decimal("1913.00")},
        },
        job_id="JOB-1",
    )
    assert record.status == "COMPLETED"
    assert record.job_id == "JOB-1"
    assert record.response_body == {
        "premium": {"basic_premium": 1900},
        "proposal": {"gross_premium": 1913},
    }
    session.flush.assert_awaited()
