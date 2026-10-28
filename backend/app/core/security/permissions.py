"""Staff permission evaluation — wildcards are a platform principal right.

``*:*`` is not a tenant permission. A poisoned role_permissions row must not
turn an agency user into a super-admin.
"""

from __future__ import annotations

PLATFORM_WILDCARD = "*:*"


def effective_permissions(*, is_platform_admin: bool, permissions: set[str]) -> set[str]:
    """Resolve live grants.

    Platform principals always receive ``*:*`` so break-glass admins keep access
    even when their assigned role row lags the catalog (e.g. new commission
    permissions). Tenant roles must never inherit a poisoned wildcard.
    """
    perms = {str(code) for code in permissions if code}
    if is_platform_admin:
        perms.add(PLATFORM_WILDCARD)
    else:
        perms.discard(PLATFORM_WILDCARD)
    return perms


def is_platform_only_permission(code: str) -> bool:
    return code == PLATFORM_WILDCARD or code.startswith("platform:")
