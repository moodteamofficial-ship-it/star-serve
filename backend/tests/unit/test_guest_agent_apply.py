"""Public agent self-registration lands PENDING and cannot set trusted fields."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import ConflictError
from app.core.security.guest_capabilities import GuestContext
from app.modules.intermediaries import guest_service
from app.modules.intermediaries.guest_service import GuestAgentApplicationService
from app.modules.intermediaries.models import Intermediary
from app.modules.intermediaries.schemas import GuestAgentApplicationRequest
from app.modules.intermediaries.uniqueness import duplicate_message

VALID = {
    "name": "Jane Wanjiku",
    "email": "Jane@Example.com",
    "phone": "+254712345678",
    "identification": "12345678",
}


def _guest() -> GuestContext:
    return GuestContext(
        session_id=uuid4(), tenant_id=uuid4(), tenant_status="ACTIVE", app_env="test"
    )


class _Session:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, row: object) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None


class _Audit:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def record(self, **kwargs: object) -> None:
        self.events.append(kwargs)


def _service(monkeypatch: pytest.MonkeyPatch, existing: dict | None = None):
    session = _Session()
    request = SimpleNamespace(
        headers={"user-agent": "pytest"}, client=None, state=SimpleNamespace()
    )
    service = GuestAgentApplicationService(session, _guest(), request)  # type: ignore[arg-type]
    service.audit = _Audit()  # type: ignore[assignment]
    taken = existing or {}

    async def fake_duplicates(_session, values, **_kwargs):
        return [key for key, value in values.items() if value and taken.get(key) == value]

    async def fake_code_taken(_session, code):
        return taken.get("agent_code") == code

    async def fake_branch(_session, _tenant_id):
        return None

    monkeypatch.setattr(guest_service, "find_duplicate_fields", fake_duplicates)
    monkeypatch.setattr(guest_service, "agent_code_taken", fake_code_taken)
    monkeypatch.setattr(guest_service, "first_active_tenant_branch_id", fake_branch)
    monkeypatch.setattr(guest_service, "client_ip", lambda _request: "203.0.113.9")
    return service, session


@pytest.mark.parametrize("field", ["status", "tenant_id", "branch_id", "notes", "approved_at"])
def test_schema_rejects_server_owned_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        GuestAgentApplicationRequest(**VALID, **{field: "APPROVED"})


def test_schema_validates_agent_code() -> None:
    assert GuestAgentApplicationRequest(**VALID, agent_code="").agent_code is None
    assert GuestAgentApplicationRequest(**VALID, agent_code="123456").agent_code == "123456"
    with pytest.raises(ValidationError):
        GuestAgentApplicationRequest(**VALID, agent_code="12ab56")


async def test_apply_inserts_pending_on_guest_agency(monkeypatch: pytest.MonkeyPatch) -> None:
    service, session = _service(monkeypatch)
    result = await service.apply(GuestAgentApplicationRequest(**VALID, agent_code="654321"))

    assert result == {"status": "PENDING"}
    assert len(session.added) == 1
    row = session.added[0]
    assert isinstance(row, Intermediary)
    assert row.status == "PENDING"
    assert row.tenant_id == service.guest.tenant_id
    assert row.created_by_user_id is None
    assert row.approved_at is None
    assert row.agent_code == "654321"
    assert row.email == "jane@example.com"
    assert service.audit.events[-1]["action"] == "intermediary.self_register"


async def test_apply_auto_generates_agent_code(monkeypatch: pytest.MonkeyPatch) -> None:
    service, session = _service(monkeypatch)
    await service.apply(GuestAgentApplicationRequest(**VALID))
    code = session.added[0].agent_code
    assert len(code) == 6 and code.isdigit()


@pytest.mark.parametrize(
    ("field", "value", "label"),
    [
        ("identification", "12345678", "National ID/Passport"),
        ("phone", "+254712345678", "phone number"),
        ("email", "jane@example.com", "email"),
        ("agent_code", "111111", "agent code"),
        ("kra_pin", "A123456789Z", "KRA PIN"),
    ],
)
async def test_duplicates_are_rejected(
    monkeypatch: pytest.MonkeyPatch, field: str, value: str, label: str
) -> None:
    service, session = _service(monkeypatch, existing={field: value})
    body = GuestAgentApplicationRequest(**VALID, agent_code="111111", kra_pin="A123456789Z")
    with pytest.raises(ConflictError) as exc:
        await service.apply(body)
    assert label in str(exc.value.message if hasattr(exc.value, "message") else exc.value)
    assert session.added == []
    assert service.audit.events[-1]["result"] == "DUPLICATE"
    assert service.audit.events[-1]["metadata"] == {"fields": [field]}


def test_duplicate_message_lists_every_clash() -> None:
    assert duplicate_message(["phone"]) == "An agent with this phone number is already registered."
    assert duplicate_message(["email", "identification", "kra_pin"]) == (
        "An agent with this National ID/Passport, email and KRA PIN are already registered."
    )


async def test_honeypot_is_silently_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    service, session = _service(monkeypatch)
    result = await service.apply(
        GuestAgentApplicationRequest(**VALID, website="http://spam.example")
    )
    assert result == {"status": "PENDING"}
    assert session.added == []
    assert service.audit.events == []


def test_phone_formats_compare_equal() -> None:
    from app.modules.intermediaries.uniqueness import phone_key, phone_variants

    assert {phone_key(v) for v in ("+254712345678", "254712345678", "0712345678", "712345678")} == {
        "254712345678"
    }
    assert "0712345678" in phone_variants("+254712345678")
