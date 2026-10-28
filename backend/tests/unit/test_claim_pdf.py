"""Official claim file PDF is generated from the desk payload."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.modules.claims.pdf import _fonts, _logo_path, render_claim_pdf

NAIROBI = ZoneInfo("Africa/Nairobi")


def _payload() -> dict:
    return {
        "claim_number": "CLM-2026-DC619C24",
        "status": "VETTING_PASSED",
        "channel": "GUEST",
        "agency_name": "Star Serve",
        "assigned_to_name": "Lawrence Larry",
        "created_at": datetime(2026, 9, 13, 15, 32, tzinfo=NAIROBI),
        "policy": {
            "policy_number": "POL-D5B361295D",
            "product_code": "3617",
            "cover_option": "TPO",
            "cover_start_date": date(2026, 9, 1),
            "cover_end_date": date(2026, 9, 30),
        },
        "claimant": {
            "name": "Lawrence Larry Trial",
            "phone": "+254700715792",
            "id_number": "88008800",
        },
        "accident": {
            "incident_date": date(2026, 9, 9),
            "incident_location": "Yaya",
            "incident_description": "Collision at the junction. Front bumper and headlamp damaged.",
        },
        "vehicle": {
            "registration": "KDV345L",
            "make": "MERCEDES BENZ",
            "model": "GLE-CLASS",
        },
        "driver": {"name": None, "license_number": None},
        "damage": {"description": None},
        "injuries": {"summary": None, "medical_notes": None},
        "financial": {
            "claimed_amount": Decimal("120000"),
            "approved_amount": None,
            "currency": "KES",
            "beneficiary_type": "CLIENT",
        },
        "vetting": [
            {
                "decision": "PASS",
                "decision_reason": "Yes i have confirmed",
                "is_current": True,
                "checklist": {
                    "claimant_verified": True,
                    "policy_active_at_incident": True,
                    "coverage_confirmed": True,
                    "documents_complete": True,
                    "accident_details_consistent": True,
                    "no_unresolved_followups": True,
                },
            }
        ],
        "approvals": [
            {
                "decision": "APPROVED",
                "reason": "Passed assessment",
                "superseded": False,
                "created_at": datetime(2026, 9, 13, 18, 49, tzinfo=NAIROBI),
            }
        ],
        "definite_reviews": [],
        "documents": [],
        "timeline": [
            {
                "action": "CLAIM_SUBMITTED",
                "summary": "Filed from the welcome screen",
                "actor_display_name": "Lawrence Larry",
                "created_at": datetime(2026, 9, 13, 18, 32, tzinfo=NAIROBI),
            }
        ],
    }


def test_logo_ships_with_the_app() -> None:
    path = _logo_path()
    assert path is not None
    assert path.name == "star-serve-logo.png"
    assert path.stat().st_size > 1000


def test_claim_pdf_uses_poppins() -> None:
    faces = _fonts()
    assert faces["regular"] == "Poppins"
    assert faces["semibold"] == "Poppins-SemiBold"
    assert faces["bold"] == "Poppins-Bold"


def test_claim_pdf_is_a_branded_document() -> None:
    content = render_claim_pdf(
        _payload(),
        letterhead={
            "agency": "Star Serve",
            "legal_name": "Star Serve Insurance Agency",
            "phone": "+254700000000",
            "email": "claims@starserve.local",
            "generated_by": "Lawrence Larry",
            "generated_by_role": "claims_officer",
        },
    )
    assert content.startswith(b"%PDF")
    assert b"Star Serve claim file CLM-2026-DC619C24" in content
    assert b"/Author (Lawrence Larry)" in content
    assert b"/Subtype /Image" in content
    assert b"/Width 1024" in content
    assert b"/Count 2" in content or b"/Count 3" in content
    assert len(content) > 80_000


def test_claim_pdf_redacts_missing_sensitive_fields() -> None:
    payload = _payload()
    payload["claimant"]["id_number"] = None
    payload["financial"]["approved_amount"] = None
    content = render_claim_pdf(payload)
    assert content.startswith(b"%PDF")
    assert b"88008800" not in content
