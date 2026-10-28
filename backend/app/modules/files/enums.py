"""Kinds of durable PDFs kept under backend/data."""

from enum import StrEnum


class StoredFileKind(StrEnum):
    CLAIM = "claim"
    CERTIFICATE = "certificate"


class StoredFileAccessKind(StrEnum):
    STORED = "STORED"
    VIEW = "VIEW"
    DOWNLOAD = "DOWNLOAD"
    EMAIL = "EMAIL"


class StoredFileSource(StrEnum):
    GUEST_SUBMIT = "guest_submit"
    STAFF = "staff"
    SYSTEM = "system"
    BACKFILL = "backfill"
