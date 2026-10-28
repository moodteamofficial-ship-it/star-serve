"""Definite-shaped motor catalog stubs for local / offline wizard flows."""

from __future__ import annotations

from typing import Any


def stub_products() -> list[dict[str, Any]]:
    """Categories + products matching the Definite motor quote UX."""
    return [
        {
            "external_id": "3532",
            "code": "MOTOR_PSV_TPO",
            "name": "Motor PSV — Third Party",
            "description": "Public service vehicle third party liability",
            "category": "Motor PSV",
            "cover_options": [
                {"id": "3191", "name": "Third Party Only"},
                {"id": "3192", "name": "Third Party Fire & Theft"},
            ],
            "provider_code": "DEFINITE_ASSURANCE",
        },
        {
            "external_id": "3533",
            "code": "MOTOR_PSV_COMP",
            "name": "Motor PSV — Comprehensive",
            "description": "Public service vehicle comprehensive cover",
            "category": "Motor PSV",
            "cover_options": [{"id": "3193", "name": "Comprehensive"}],
            "provider_code": "DEFINITE_ASSURANCE",
        },
        {
            "external_id": "4688",
            "code": "CARS_TPO",
            "name": "Private Cars — Third Party",
            "description": "Private motor third party",
            "category": "Cars",
            "cover_options": [
                {"id": "3493", "name": "Third Party Only"},
                {"id": "3494", "name": "Third Party Fire & Theft"},
            ],
            "provider_code": "DEFINITE_ASSURANCE",
        },
        {
            "external_id": "4689",
            "code": "CARS_COMP",
            "name": "Private Cars — Comprehensive",
            "description": "Private motor comprehensive",
            "category": "Cars",
            "cover_options": [{"id": "3495", "name": "Comprehensive"}],
            "provider_code": "DEFINITE_ASSURANCE",
        },
        {
            "external_id": "4701",
            "code": "MOTO_TPO",
            "name": "Motorcycle — Third Party",
            "description": "Motorcycle third party",
            "category": "Motorcycle",
            "cover_options": [{"id": "3601", "name": "Third Party Only"}],
            "provider_code": "DEFINITE_ASSURANCE",
        },
        {
            "external_id": "4702",
            "code": "MOTO_COMP",
            "name": "Motorcycle — Comprehensive",
            "description": "Motorcycle comprehensive",
            "category": "Motorcycle",
            "cover_options": [{"id": "3602", "name": "Comprehensive"}],
            "provider_code": "DEFINITE_ASSURANCE",
        },
        {
            "external_id": "4703",
            "code": "MOTO_PILLION",
            "name": "Motorcycle — Pillion",
            "description": "Motorcycle with pillion liability",
            "category": "Motorcycle",
            "cover_options": [{"id": "3603", "name": "Pillion Cover"}],
            "provider_code": "DEFINITE_ASSURANCE",
        },
        {
            "external_id": "4704",
            "code": "MOTO_DELIVERY",
            "name": "Motorcycle — Delivery",
            "description": "Commercial delivery motorcycle",
            "category": "Motorcycle",
            "cover_options": [{"id": "3604", "name": "Delivery"}],
            "provider_code": "DEFINITE_ASSURANCE",
        },
        {
            "external_id": "4801",
            "code": "COMM_TPO",
            "name": "Commercial Motor — TPO",
            "description": "Commercial vehicle third party",
            "category": "Motor Commercial",
            "cover_options": [{"id": "3701", "name": "Third Party Only"}],
            "provider_code": "DEFINITE_ASSURANCE",
        },
        {
            "external_id": "4802",
            "code": "COMM_COMP",
            "name": "Commercial Motor — Comprehensive",
            "description": "Commercial vehicle comprehensive",
            "category": "Motor Commercial",
            "cover_options": [{"id": "3702", "name": "Comprehensive"}],
            "provider_code": "DEFINITE_ASSURANCE",
        },
        {
            "external_id": "4803",
            "code": "COMM_GOODS",
            "name": "Commercial Motor — Goods",
            "description": "Goods carrying commercial motor",
            "category": "Motor Commercial",
            "cover_options": [{"id": "3703", "name": "Goods Carrying"}],
            "provider_code": "DEFINITE_ASSURANCE",
        },
        {
            "external_id": "4804",
            "code": "COMM_OWN_GOODS",
            "name": "Commercial Motor — Own Goods",
            "description": "Own goods commercial motor",
            "category": "Motor Commercial",
            "cover_options": [{"id": "3704", "name": "Own Goods"}],
            "provider_code": "DEFINITE_ASSURANCE",
        },
        {
            "external_id": "4901",
            "code": "PRIVATE_HIRE_TPO",
            "name": "Private Hire — Third Party",
            "description": "Private hire third party",
            "category": "Private Hire",
            "cover_options": [{"id": "3801", "name": "Third Party Only"}],
            "provider_code": "DEFINITE_ASSURANCE",
        },
        {
            "external_id": "4902",
            "code": "PRIVATE_HIRE_COMP",
            "name": "Private Hire — Comprehensive",
            "description": "Private hire comprehensive",
            "category": "Private Hire",
            "cover_options": [{"id": "3802", "name": "Comprehensive"}],
            "provider_code": "DEFINITE_ASSURANCE",
        },
        {
            "external_id": "5001",
            "code": "TUK_TUK_PSV",
            "name": "Tuk Tuk PSV — Portal",
            "description": "Tuk tuk public service vehicle",
            "category": "Tuk Tuk",
            "cover_options": [{"id": "3901", "name": "Third Party Only"}],
            "provider_code": "DEFINITE_ASSURANCE",
        },
        {
            "external_id": "5002",
            "code": "TUK_TUK_COMM",
            "name": "Tuk Tuk — Commercial",
            "description": "Commercial tuk tuk",
            "category": "Tuk Tuk",
            "cover_options": [{"id": "3902", "name": "Third Party Only"}],
            "provider_code": "DEFINITE_ASSURANCE",
        },
    ]


def stub_makes() -> list[dict[str, Any]]:
    return [
        {
            "external_id": "1",
            "code": "1",
            "name": "Toyota",
            "sort_order": 10,
            "models": [
                {"id": "10", "name": "Corolla"},
                {"id": "11", "name": "Hilux"},
                {"id": "12", "name": "Premio"},
            ],
            "provider_code": "DEFINITE_ASSURANCE",
        },
        {
            "external_id": "2",
            "code": "2",
            "name": "Nissan",
            "sort_order": 20,
            "models": [
                {"id": "20", "name": "Note"},
                {"id": "21", "name": "X-Trail"},
            ],
            "provider_code": "DEFINITE_ASSURANCE",
        },
        {
            "external_id": "3",
            "code": "3",
            "name": "Isuzu",
            "sort_order": 30,
            "models": [
                {"id": "30", "name": "D-Max"},
                {"id": "31", "name": "NQR"},
            ],
            "provider_code": "DEFINITE_ASSURANCE",
        },
        {
            "external_id": "4",
            "code": "4",
            "name": "Honda",
            "sort_order": 40,
            "models": [
                {"id": "40", "name": "Fit"},
                {"id": "41", "name": "CR-V"},
            ],
            "provider_code": "DEFINITE_ASSURANCE",
        },
        {
            "external_id": "5",
            "code": "5",
            "name": "Subaru",
            "sort_order": 50,
            "models": [
                {"id": "50", "name": "Impreza"},
                {"id": "51", "name": "Forester"},
            ],
            "provider_code": "DEFINITE_ASSURANCE",
        },
    ]


_CATEGORY_ORDER = (
    "Tuk Tuk",
    "Motor PSV",
    "Cars",
    "Motorcycle",
    "Motor Commercial",
    "Private Hire",
)


def _effective_category(product: dict[str, Any]) -> str:
    """Prefer name-based Tuk Tuk (and keep provider category otherwise)."""
    name = str(product.get("name") or "")
    upper = " ".join(name.upper().split())
    tokens = set(
        upper.replace("-", " ").replace("(", " ").replace(")", " ").replace(",", " ").split()
    )
    if "TUK" in tokens or "TUKTUK" in tokens:
        return "Tuk Tuk"
    return str(product.get("category") or "Other")


def group_catalog(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for product in products:
        cat = _effective_category(product)
        row = product if product.get("category") == cat else {**product, "category": cat}
        groups.setdefault(cat, []).append(row)
    ordered_keys = [c for c in _CATEGORY_ORDER if c in groups]
    ordered_keys.extend(sorted(c for c in groups if c not in _CATEGORY_ORDER))
    return [
        {"category": category, "product_count": len(groups[category]), "products": groups[category]}
        for category in ordered_keys
    ]
