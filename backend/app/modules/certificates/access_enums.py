"""Certificate file access kinds — who touched which PDF and when."""

from enum import StrEnum


class CertificateAccessKind(StrEnum):
    STORED = "STORED"
    VIEW = "VIEW"
    DOWNLOAD = "DOWNLOAD"
    OPEN_REMOTE = "OPEN_REMOTE"
    FETCH_FAILED = "FETCH_FAILED"


class CertificateAccessSource(StrEnum):
    LOCAL = "local"
    REMOTE_PROVIDER = "remote_provider"
    SYSTEM = "system"
