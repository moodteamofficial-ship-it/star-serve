"""JSON helpers for JSONB columns and request hashing.

Python ``json`` (and SQLAlchemy's default JSON serializer) cannot encode
``Decimal``, ``UUID``, or ``datetime``. Guest issuance stores those types
on ``idempotency_keys.response_body``.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID


def json_ready(value: Any) -> Any:
    """Return a tree of JSON-native types (dict/list/str/int/float/bool/None)."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, Enum):
        return json_ready(value.value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_ready(item) for item in value]
    return str(value)


def dumps_jsonb(value: Any) -> str:
    """SQLAlchemy ``json_serializer`` for JSON/JSONB columns."""
    return json.dumps(json_ready(value), ensure_ascii=False)
