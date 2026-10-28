"""Insurer catalog mirror — shape, change detection, refresh rules (no DB)."""

from datetime import UTC, datetime, timedelta

from app.integrations.insurance.catalog_stub import group_catalog, stub_makes, stub_products
from app.integrations.insurance.factory import NullInsuranceProvider, ResilientInsuranceProvider
from app.modules.guest.insurance_gateway import GuestInsuranceGateway
from app.modules.insurer_catalog import service as svc


def test_normalized_catalog_matches_previous_live_shape() -> None:
    products = svc._normalize_products(stub_products())  # noqa: SLF001
    makes = svc._normalize_makes(stub_makes())  # noqa: SLF001
    payload = svc.catalog_payload(svc.CatalogSnapshot(products=products, makes=makes), "database")

    previous = group_catalog(stub_products())
    assert [(c["category"], c["product_count"]) for c in payload["categories"]] == [
        (c["category"], c["product_count"]) for c in previous
    ]
    assert [c["category"] for c in payload["categories"]][:6] == [
        "Tuk Tuk",
        "Motor PSV",
        "Cars",
        "Motorcycle",
        "Motor Commercial",
        "Private Hire",
    ]
    for new, old in zip(payload["products"], stub_products(), strict=True):
        for key in ("external_id", "code", "name", "description", "category", "cover_options"):
            assert new[key] == old[key]
    for new, old in zip(payload["makes"], stub_makes(), strict=True):
        for key in ("external_id", "code", "name", "models"):
            assert new[key] == old[key]


def test_normalize_drops_invalid_and_duplicate_rows() -> None:
    rows = svc._normalize_products(  # noqa: SLF001
        [
            {"external_id": "1", "name": "A", "cover_options": [{"id": "c", "name": "C"}] * 2},
            {"external_id": "1", "name": "A again"},
            {"external_id": "", "name": "no id"},
            {"external_id": "2"},
            "junk",
        ]
    )
    assert [r["external_id"] for r in rows] == ["1"]
    assert rows[0]["cover_options"] == [{"id": "c", "name": "C"}]
    assert svc._normalize_products(None) == []  # noqa: SLF001
    assert svc._normalize_makes({"not": "a list"}) == []  # noqa: SLF001


def test_content_hash_detects_only_real_changes() -> None:
    base = svc._normalize_products(stub_products())  # noqa: SLF001
    same = svc._normalize_products(stub_products())  # noqa: SLF001
    assert svc.content_hash(base) == svc.content_hash(same)

    renamed = svc._normalize_products(stub_products())  # noqa: SLF001
    renamed[0]["cover_options"][0]["name"] = "Third Party Only (TPO)"
    assert svc.content_hash(base) != svc.content_hash(renamed)


def test_staleness_and_failure_backoff() -> None:
    now = datetime.now(UTC)
    assert svc.is_stale(svc.CatalogSnapshot(), now=now)
    fresh = svc.CatalogSnapshot(last_success_at=now - timedelta(minutes=5))
    assert not svc.is_stale(fresh, now=now)
    old = svc.CatalogSnapshot(last_success_at=now - timedelta(hours=2))
    assert svc.is_stale(old, now=now)
    just_failed = svc.CatalogSnapshot(
        last_success_at=now - timedelta(hours=2), last_attempt_at=now - timedelta(minutes=1)
    )
    assert not svc.is_stale(just_failed, now=now)


def test_sync_reads_the_real_insurer_not_the_stub_fallback() -> None:
    real = NullInsuranceProvider()
    resilient = ResilientInsuranceProvider(real, NullInsuranceProvider())
    assert svc.catalog_source(resilient) is real
    assert svc.catalog_source(GuestInsuranceGateway(resilient)) is real
    assert svc.catalog_source(real) is real


def test_memo_roundtrip() -> None:
    svc.forget()
    assert svc.recall() is None
    snap = svc.CatalogSnapshot(products=[{"external_id": "1"}], makes=[{"external_id": "m"}])
    svc.remember(snap)
    assert svc.recall() is snap
    svc.forget()
    assert svc.recall() is None
