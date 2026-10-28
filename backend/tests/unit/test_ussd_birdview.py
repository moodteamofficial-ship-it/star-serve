"""Birdview partner contract — GET params, CON/END plain text, latest-only INPUT."""

from starlette.requests import Request

from app.modules.ussd.enums import UssdProviderKind
from app.modules.ussd.providers.birdview import (
    BIRDVIEW_MAX_CHARS,
    BirdviewAdapter,
    looks_like_birdview,
    normalize_birdview_input,
    normalize_ussd_code,
)


def _request(path: str = "/api/v1/ussd/callback", query: str = "") -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": [],
        "client": ("203.0.113.10", 443),
        "server": ("test", 443),
    }
    return Request(scope)


def test_normalize_ussd_code():
    assert normalize_ussd_code("*652*6#") == "*652*6#"
    assert normalize_ussd_code("652*6") == "*652*6#"
    assert normalize_ussd_code("") == ""


def test_looks_like_birdview_from_query():
    req = _request(
        query="SESSIONID=abc123&MSISDN=%2B254712345678&USSDCODE=%2A652%2A6%23&INPUT="
    )
    assert looks_like_birdview(req) is True
    assert looks_like_birdview(_request(query="sessionId=x")) is False


async def test_parse_empty_input_is_welcome_signal():
    adapter = BirdviewAdapter()
    req = _request(
        query="SESSIONID=1234567890123&MSISDN=%2B254712345678&USSDCODE=%2A652%2A6%23&INPUT="
    )
    callback = await adapter.parse(req)
    assert callback.provider_kind == UssdProviderKind.BIRDVIEW.value
    assert callback.session_id == "1234567890123"
    assert callback.msisdn == "+254712345678"
    assert callback.service_code == "*652*6#"
    assert callback.text == ""


async def test_parse_latest_input_only_not_cumulative():
    adapter = BirdviewAdapter()
    req = _request(
        query="SESSIONID=s1&MSISDN=%2B254700000000&USSDCODE=%2A652%2A6%23&INPUT=4321"
    )
    callback = await adapter.parse(req)
    assert callback.text == "4321"
    assert "*" not in (callback.text or "")


def test_normalize_birdview_input_strips_live_cumulative_trail():
    # Live evidence SESSIONID=213348490: INPUT=1*0 after choosing motor then Back.
    assert normalize_birdview_input("1*0") == "0"
    assert normalize_birdview_input("1*2*3") == "3"
    assert normalize_birdview_input("1") == "1"
    assert normalize_birdview_input("") == ""
    assert normalize_birdview_input(None) is None


async def test_parse_live_cumulative_input_uses_last_segment():
    adapter = BirdviewAdapter()
    req = _request(
        query="SESSIONID=213348490&MSISDN=%2B254700715792&USSDCODE=%2A652%23&INPUT=1%2A0"
    )
    callback = await adapter.parse(req)
    assert callback.text == "0"
    assert callback.service_code == "*652#"


def test_render_con_and_end_plain_text():
    adapter = BirdviewAdapter()
    con = adapter.render(text="Welcome\n1. Quote\n2. Claim", response_type="CONTINUE")
    assert con.status_code == 200
    assert con.media_type.startswith("text/plain")
    assert con.body.decode().startswith("CON Welcome")
    assert "\n1. Quote" in con.body.decode()

    end = adapter.render(text="Thank you.", response_type="END")
    assert end.status_code == 200
    assert end.body.decode() == "END Thank you."


def test_render_strips_accidental_prefix_and_clamps_length():
    adapter = BirdviewAdapter()
    long_text = "A" * 300
    res = adapter.render(text=f"CON {long_text}", response_type="CONTINUE")
    body = res.body.decode()
    assert body.startswith("CON ")
    assert not body.startswith("CON CON")
    # Prefix + space + content <= CON_ + 160 chars
    content = body[4:]
    assert len(content) <= BIRDVIEW_MAX_CHARS


def test_render_unavailable_always_end():
    adapter = BirdviewAdapter()
    res = adapter.render_unavailable()
    assert res.status_code == 200
    assert res.body.decode().startswith("END Service temporarily unavailable")
