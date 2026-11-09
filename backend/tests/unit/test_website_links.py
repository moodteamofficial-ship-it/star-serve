import pytest

from app.core.exceptions import ValidationAppError
from app.modules.website.links import QUOTE_BASE, resolve_link


def test_resolve_internal():
    assert resolve_link("internal", "/services") == "/services"


def test_resolve_quote_defaults():
    assert resolve_link("quote", "") == QUOTE_BASE + "/"


def test_resolve_quote_product():
    url = resolve_link("quote_product", "motor-insurance")
    assert url == QUOTE_BASE + "/?product=motor"


def test_resolve_external_requires_https():
    assert resolve_link("external", "https://example.com") == "https://example.com"
    with pytest.raises(ValidationAppError):
        resolve_link("external", "javascript:alert(1)")
