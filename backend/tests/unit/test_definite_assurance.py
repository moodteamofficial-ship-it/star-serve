"""Phase 3 Definite Assurance unit tests — mocked HTTP, no live provider calls."""

import pytest
from httpx import Response

from app.integrations.insurance.definite_assurance.client import (
    CircuitBreaker,
    DefiniteAssuranceClient,
)
from app.integrations.insurance.definite_assurance.exceptions import (
    DefiniteAssuranceUnavailable,
)
from app.integrations.insurance.definite_assurance.mapper import (
    map_client,
    map_makes,
    map_premium,
    map_products,
)
from app.integrations.insurance.definite_assurance.service import DefiniteAssuranceProvider


def test_classify_client_lookup_fail_closed() -> None:
    from app.integrations.insurance.definite_assurance.mapper import classify_client_lookup

    assert classify_client_lookup(None) == "ABSENT"
    assert classify_client_lookup({}) == "ABSENT"
    assert classify_client_lookup({"message": "Client not found"}) == "ABSENT"
    assert (
        classify_client_lookup(
            {"data": {"firstName": "Ada", "idNumber": "12345678", "OID": 9}}
        )
        == "FOUND"
    )
    assert classify_client_lookup({"success": True, "clients": [{"x": 1}]}) == "UNKNOWN"


def test_map_client_and_products() -> None:
    client = map_client(
        {"data": {"firstName": "Ada", "lastName": "Lovelace", "idNumber": "12345678", "clientId": "C1"}}
    )
    assert client is not None
    assert client["first_name"] == "Ada"
    assert client["external_ref"] == "C1"
    products = map_products([{"code": "MOTOR", "name": "Motor", "coverOptions": ["TPO"]}])
    assert products[0]["code"] == "MOTOR"
    assert products[0]["category"] == "Cars"
    makes = map_makes(["Toyota", {"code": "NISSAN", "name": "Nissan"}])
    assert len(makes) == 2
    premium = map_premium({"basicPremium": 1000, "grossPremium": 1150, "PHCF": 20})
    assert premium["gross_premium"] == 1150.0


def test_category_from_live_product_names() -> None:
    rows = [
        {"code": "1", "name": "PRIVATE HIRE - CHAUFFER DRIVEN", "coverOptions": []},
        {"code": "2", "name": "MOTOR PSV - BUSES(TPO ONLY)", "coverOptions": []},
        {"code": "3", "name": "MOTOR COMM - AGRICULTURAL", "coverOptions": []},
        {
            "code": "4",
            "name": "MOTOR COMMERICIAL HYBRID(OWN GOODS,GENERAL CARTAGE)",
            "coverOptions": [],
        },
        {"code": "5", "name": "MOTOR PRIVATE - PORTAL", "coverOptions": []},
        {"code": "6", "name": "MOTOR CYCLE BODA - PORTAL", "coverOptions": []},
        {"code": "7", "name": "TUK TUK PSV - PORTAL", "coverOptions": []},
        {"code": "8", "name": "TUK TUK - COMMERCIAL", "coverOptions": []},
    ]
    mapped = {p["name"]: p["category"] for p in map_products(rows)}
    assert mapped["PRIVATE HIRE - CHAUFFER DRIVEN"] == "Private Hire"
    assert mapped["MOTOR PSV - BUSES(TPO ONLY)"] == "Motor PSV"
    assert mapped["MOTOR COMM - AGRICULTURAL"] == "Motor Commercial"
    assert mapped["MOTOR COMMERICIAL HYBRID(OWN GOODS,GENERAL CARTAGE)"] == "Motor Commercial"
    assert mapped["MOTOR PRIVATE - PORTAL"] == "Cars"
    assert mapped["MOTOR CYCLE BODA - PORTAL"] == "Motorcycle"
    assert mapped["TUK TUK PSV - PORTAL"] == "Tuk Tuk"
    assert mapped["TUK TUK - COMMERCIAL"] == "Tuk Tuk"
    assert "Motor" not in mapped.values()


def test_circuit_breaker_opens() -> None:
    cb = CircuitBreaker(failure_threshold=2, recovery_seconds=60)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "OPEN"
    with pytest.raises(DefiniteAssuranceUnavailable):
        cb.before_call()


@pytest.mark.asyncio
async def test_provider_check_client_uses_mapper(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        async def get(self, path: str, *, params=None, retryable: bool = True):
            assert path == "checkClient"
            assert params == {"IDNumber": "12345678"}
            return {"firstName": "Jane", "lastName": "Doe", "idNumber": "12345678", "id": "X1"}

        async def post(self, *args, **kwargs):
            raise AssertionError("post should not be called")

    provider = DefiniteAssuranceProvider(client=FakeClient())  # type: ignore[arg-type]
    result = await provider.check_client(id_number="12345678")
    assert result is not None
    assert result["first_name"] == "Jane"
    assert result["external_ref"] == "X1"


@pytest.mark.asyncio
async def test_provider_check_client_unknown_shape_fails_closed() -> None:
    from app.integrations.insurance.definite_assurance.exceptions import (
        DefiniteAssuranceError,
    )

    class FakeClient:
        async def get(self, path: str, *, params=None, retryable: bool = True):
            return {"success": True, "clients": [{"nested": True}]}

        async def post(self, *args, **kwargs):
            raise AssertionError("post should not be called")

    provider = DefiniteAssuranceProvider(client=FakeClient())  # type: ignore[arg-type]
    with pytest.raises(DefiniteAssuranceError, match="unreadable"):
        await provider.check_client(id_number="12345678")


@pytest.mark.asyncio
async def test_client_maps_timeout_to_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    class BoomTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> Response:
            raise httpx.ConnectTimeout("timeout")

    settings = type(
        "S",
        (),
        {
            "definite_assurance_base_url": "https://uat.definiteassurance.com/api/v1",
            "definite_assurance_username": "user",
            "definite_assurance_password": "pass",
            "definite_assurance_timeout_seconds": 1,
        },
    )()
    transport = BoomTransport()
    http = httpx.AsyncClient(transport=transport, base_url="https://example.test/")
    client = DefiniteAssuranceClient(settings=settings, http_client=http)  # type: ignore[arg-type]
    with pytest.raises(DefiniteAssuranceUnavailable):
        await client.get("products", retryable=False)
    await http.aclose()


@pytest.mark.asyncio
async def test_provider_create_client_sends_email() -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        async def get(self, *args, **kwargs):
            raise AssertionError("get should not be called")

        async def post(self, path: str, *, json_body=None, **kwargs):
            assert path == "createClient"
            captured["body"] = json_body
            return {"data": {"firstName": "Ada", "lastName": "Lovelace", "idNumber": "12345678", "OID": 42}}

    provider = DefiniteAssuranceProvider(client=FakeClient())  # type: ignore[arg-type]
    result = await provider.create_client(
        {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "id_number": "12345678",
            "phone": "254712345678",
            "email": "Ada@Example.com",
        }
    )
    assert result["external_ref"] == "42"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["email"] == "ada@example.com"
    assert body["phone"] == "254712345678"


def test_public_definite_message_hides_node_sandbox_stacks() -> None:
    from app.integrations.insurance.definite_assurance.client import public_definite_message

    raw = (
        "TypeError: fetch failed at node:internal/deps/undici/undici:12637:11 "
        "at async D:\\applications\\sandbox\\index.js:3378:32"
    )
    cleaned = public_definite_message(raw)
    assert "undici" not in cleaned.lower()
    assert "index.js" not in cleaned.lower()
    assert "insurer" in cleaned.lower()
