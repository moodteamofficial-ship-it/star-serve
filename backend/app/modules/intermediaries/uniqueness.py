"""One agent per phone, ID, agent code, email, and KRA PIN — across every tenant.

Agent codes resolve globally on QR scan and platform-created agents re-home onto
the agency, so a per-tenant check would still let two agents collide. Lookups
run with a short RLS bypass and return only which fields clash, never the row.
"""

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.rls import set_rls_bypass
from app.core.exceptions import ConflictError
from app.modules.intermediaries.models import Intermediary

FIELD_LABELS: dict[str, str] = {
    "identification": "National ID/Passport",
    "phone": "phone number",
    "email": "email",
    "agent_code": "agent code",
    "kra_pin": "KRA PIN",
}


def phone_key(value: str) -> str:
    """Kenyan numbers compare equal whether typed as +254…, 254…, 07…, or 7…."""
    digits = value.strip().lstrip("+").replace(" ", "")
    if digits.startswith("254") and len(digits) == 12:
        return digits
    if digits.startswith("0") and len(digits) == 10:
        return f"254{digits[1:]}"
    if len(digits) == 9 and digits[0] in "17":
        return f"254{digits}"
    return digits


def phone_variants(value: str) -> list[str]:
    key = phone_key(value)
    if key.startswith("254") and len(key) == 12:
        local = key[3:]
        return [f"+{key}", key, f"0{local}", local]
    return [value]


def _join(labels: list[str]) -> str:
    if len(labels) <= 1:
        return "".join(labels)
    return f"{', '.join(labels[:-1])} and {labels[-1]}"


def duplicate_message(fields: list[str]) -> str:
    labels = [FIELD_LABELS[name] for name in FIELD_LABELS if name in fields]
    noun = "is" if len(labels) == 1 else "are"
    return f"An agent with this {_join(labels)} {noun} already registered."


async def find_duplicate_fields(
    session: AsyncSession,
    values: dict[str, str | None],
    *,
    exclude_id: UUID | None = None,
) -> list[str]:
    wanted = {key: value for key, value in values.items() if key in FIELD_LABELS and value}
    if not wanted:
        return []

    def column(name: str):
        col = getattr(Intermediary, name)
        return func.lower(col) if name == "email" else col

    def key(name: str, value: str) -> str:
        if name == "email":
            return value.lower()
        if name == "phone":
            return phone_key(value)
        return value

    clauses = [
        column(name).in_(phone_variants(value))
        if name == "phone"
        else column(name) == key(name, value)
        for name, value in wanted.items()
    ]
    stmt = select(*(getattr(Intermediary, name) for name in wanted)).where(
        Intermediary.deleted_at.is_(None), or_(*clauses)
    )
    if exclude_id is not None:
        stmt = stmt.where(Intermediary.id != exclude_id)

    await set_rls_bypass(session, True)
    try:
        rows = (await session.execute(stmt.limit(20))).all()
    finally:
        await set_rls_bypass(session, False)

    clashes: set[str] = set()
    for row in rows:
        for name, existing in zip(wanted, row, strict=True):
            if existing is not None and key(name, str(existing)) == key(name, wanted[name]):
                clashes.add(name)
    return [name for name in FIELD_LABELS if name in clashes]


async def ensure_unique_agent(
    session: AsyncSession,
    values: dict[str, str | None],
    *,
    exclude_id: UUID | None = None,
) -> None:
    clashes = await find_duplicate_fields(session, values, exclude_id=exclude_id)
    if clashes:
        raise ConflictError(duplicate_message(clashes))


async def agent_code_taken(session: AsyncSession, code: str) -> bool:
    return bool(await find_duplicate_fields(session, {"agent_code": code}))
