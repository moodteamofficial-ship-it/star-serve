from app.modules.policies.repository import compact_alnum


def test_compact_alnum_matches_plates_and_policy_numbers() -> None:
    assert compact_alnum("KDV 345L") == "KDV345L"
    assert compact_alnum("kdv-345l") == "KDV345L"
    assert compact_alnum("POL-D5B361295D") == "POLD5B361295D"
    assert compact_alnum("pol d5b361295d") == "POLD5B361295D"
    assert compact_alnum("NW2026131278") == "NW2026131278"
    assert compact_alnum("nw 2026/131278") == "NW2026131278"
