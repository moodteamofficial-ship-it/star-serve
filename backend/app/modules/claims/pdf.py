"""Official Star Serve claim file PDF — letterhead, facts, and desk history."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak,
    Flowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAIROBI = ZoneInfo("Africa/Nairobi")

GREEN = colors.HexColor("#30A82C")
GREEN_DEEP = colors.HexColor("#248220")
INK = colors.HexColor("#161616")
MUTED = colors.HexColor("#5C5C5C")
LINE = colors.HexColor("#C8E4C6")
SOFT = colors.HexColor("#E7F6E6")
RULE = colors.HexColor("#D5EBD3")

STATUS_LABELS = {
    "CLAIM_DRAFT": "Draft",
    "CLAIM_SUBMITTED": "New report",
    "VETTING": "Under assessment",
    "ADDITIONAL_INFORMATION_REQUIRED": "Awaiting information",
    "VETTING_PASSED": "Assessment passed",
    "VETTING_FAILED": "Assessment failed",
    "SENT_TO_DEFINITE": "Sent to insurer",
    "DEFINITE_REVIEW": "With insurer",
    "DEFINITE_APPROVED": "Insurer approved",
    "DEFINITE_REJECTED": "Insurer declined",
    "PAYMENT_PENDING": "Payment pending",
    "PAYMENT_AUTHORIZATION": "Payment authorization",
    "PAYMENT_AUTHORIZED": "Payment authorized",
    "PAYMENT_PROCESSING": "Payment processing",
    "PAYMENT_COMPLETED": "Paid",
    "PAYMENT_FAILED": "Payment failed",
    "PAYMENT_REVIEW": "Payment review",
    "CLIENT_NOTIFIED": "Client notified",
    "CLOSED": "Closed",
    "REJECTED": "Declined",
    "CANCELLED": "Cancelled",
    "WITHDRAWN": "Withdrawn",
}

ACTIVITY_TITLES = {
    "CLAIM_CREATED": "Opened the file",
    "CLAIM_OPENED": "Viewed the file",
    "CLAIM_SUBMITTED": "Submitted for assessment",
    "CLAIM_ASSIGNED": "Assigned the file",
    "VETTING_STARTED": "Started assessment",
    "VETTING_PASSED": "Passed assessment",
    "VETTING_FAILED": "Failed assessment",
    "VETTING_COMPLETED": "Asked for more information",
    "FOLLOWUP_CREATED": "Added a task",
    "FOLLOWUP_COMPLETED": "Completed a task",
    "DOCUMENT_UPLOADED": "Uploaded a document",
    "DOCUMENT_DOWNLOADED": "Downloaded a document",
    "CLAIM_PDF_OPENED": "Opened the claim PDF",
    "CLAIM_PDF_DOWNLOADED": "Downloaded the claim PDF",
    "CLAIM_FORWARDED_TO_DEFINITE": "Sent to the insurer",
    "DEFINITE_RESPONSE_RECEIVED": "Insurer replied",
    "CLAIM_APPROVED": "Approved",
    "CLAIM_REJECTED": "Declined",
    "PAYMENT_INITIATED": "Started payment",
    "PAYMENT_AUTHORIZED": "Authorized payment",
    "PAYMENT_COMPLETED": "Paid",
    "PAYMENT_FAILED": "Payment failed",
    "CLAIM_CLOSED": "Closed the file",
    "CLIENT_NOTIFIED": "Notified the client",
}

VETTING_CHECKS = {
    "claimant_verified": "Claimant matches the policy",
    "policy_active_at_incident": "Policy was in force on the incident date",
    "coverage_confirmed": "This loss is covered",
    "documents_complete": "Required documents are on file",
    "accident_details_consistent": "Accident details are consistent",
    "no_unresolved_followups": "No open tasks left",
}

VETTING_DECISIONS = {
    "PASS": "Passed",
    "FAIL": "Failed",
    "MORE_INFORMATION_REQUIRED": "More information needed",
}


def _logo_path() -> Path | None:
    path = (
        Path(__file__).resolve().parents[2] / "assets" / "branding" / "star-serve-logo.png"
    )
    return path if path.is_file() else None


_FONTS: dict[str, str] | None = None


def _fonts() -> dict[str, str]:
    """Register Poppins once. Fall back to Helvetica if the files are missing."""
    global _FONTS
    if _FONTS is not None:
        return _FONTS
    names = {
        "regular": "Helvetica",
        "semibold": "Helvetica-Bold",
        "bold": "Helvetica-Bold",
    }
    root = Path(__file__).resolve().parents[2] / "assets" / "fonts"
    files = {
        "regular": (root / "Poppins-Regular.ttf", "Poppins"),
        "semibold": (root / "Poppins-SemiBold.ttf", "Poppins-SemiBold"),
        "bold": (root / "Poppins-Bold.ttf", "Poppins-Bold"),
    }
    try:
        for key, (path, face) in files.items():
            if path.is_file():
                pdfmetrics.registerFont(TTFont(face, str(path)))
                names[key] = face
        if names["regular"] == "Poppins":
            pdfmetrics.registerFontFamily(
                "Poppins",
                normal="Poppins",
                bold=names["bold"],
            )
    except Exception:
        names = {
            "regular": "Helvetica",
            "semibold": "Helvetica-Bold",
            "bold": "Helvetica-Bold",
        }
    _FONTS = names
    return names


def _plain(value: Any, fallback: str = "—") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _pretty(value: Any, fallback: str = "—") -> str:
    text = _plain(value, "")
    if not text:
        return fallback
    return text.replace("_", " ").lower().title()


def _status_label(status: Any) -> str:
    key = _plain(status, "").upper()
    return STATUS_LABELS.get(key, _pretty(status))


def _source_label(channel: Any) -> str:
    key = _plain(channel, "").upper()
    if key == "GUEST":
        return "Guest report"
    if key == "CLIENT":
        return "Client portal"
    return "Staff report"


def _pay_to(value: Any) -> tuple[str, str]:
    key = _plain(value, "").upper()
    if key == "CLIENT":
        return "Policyholder", "Insurer pays the client directly"
    if key == "STAR_SERVE":
        return "Agency", "Insurer pays the agency, then the agency pays the client"
    return _pretty(value), ""


def _money(value: Any, currency: Any = "KES") -> str:
    if value is None or value == "":
        return "—"
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return _plain(value)
    quantized = amount.quantize(Decimal("0.01")) if amount % 1 else amount.quantize(Decimal("1"))
    formatted = f"{quantized:,.2f}" if quantized % 1 else f"{int(quantized):,}"
    return f"{_plain(currency, 'KES')} {formatted}"


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=NAIROBI)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=NAIROBI)
    text = _plain(value, "")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=NAIROBI)
    return parsed


def _day(value: Any) -> str:
    parsed = _as_datetime(value)
    if parsed is None:
        return _plain(value)
    local = parsed.astimezone(NAIROBI)
    return f"{local.day} {local.strftime('%b %Y')}"


def _clock(value: Any) -> str:
    parsed = _as_datetime(value)
    if parsed is None:
        return ""
    return parsed.astimezone(NAIROBI).strftime("%H:%M")


def _when(value: Any) -> str:
    parsed = _as_datetime(value)
    if parsed is None:
        return _plain(value)
    local = parsed.astimezone(NAIROBI)
    return f"{local.day} {local.strftime('%b %Y, %H:%M')}"


def _join(*parts: Any, sep: str = " · ") -> str:
    items = [_plain(part, "") for part in parts]
    return sep.join(item for item in items if item) or "—"


def _escape(value: Any) -> str:
    text = _plain(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def _activity_title(event: dict[str, Any]) -> str:
    action = _plain(event.get("action"), "").upper()
    summary = _plain(event.get("summary"), "")
    if action == "CLAIM_SUBMITTED" and "welcome screen" in summary.lower():
        return "Filed from the welcome screen"
    if action == "CLAIM_EDITED":
        return summary or "Updated the file"
    return ACTIVITY_TITLES.get(action) or summary or _pretty(action)


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    face = _fonts()
    return {
        "doc_title": ParagraphStyle(
            "ClaimDocTitle",
            parent=base["Normal"],
            fontName=face["bold"],
            fontSize=13,
            leading=16,
            textColor=GREEN_DEEP,
            alignment=TA_RIGHT,
        ),
        "doc_sub": ParagraphStyle(
            "ClaimDocSub",
            parent=base["Normal"],
            fontName=face["regular"],
            fontSize=8,
            leading=11,
            textColor=MUTED,
            alignment=TA_RIGHT,
        ),
        "hero_ref": ParagraphStyle(
            "ClaimHeroRef",
            parent=base["Normal"],
            fontName=face["semibold"],
            fontSize=9,
            leading=12,
            textColor=GREEN_DEEP,
        ),
        "hero_name": ParagraphStyle(
            "ClaimHeroName",
            parent=base["Normal"],
            fontName=face["bold"],
            fontSize=15,
            leading=18,
            textColor=INK,
        ),
        "hero_status": ParagraphStyle(
            "ClaimHeroStatus",
            parent=base["Normal"],
            fontName=face["semibold"],
            fontSize=10,
            leading=13,
            textColor=GREEN_DEEP,
            alignment=TA_RIGHT,
        ),
        "section_n": ParagraphStyle(
            "ClaimSectionN",
            parent=base["Normal"],
            fontName=face["bold"],
            fontSize=7.5,
            leading=10,
            textColor=colors.white,
        ),
        "section_title": ParagraphStyle(
            "ClaimSectionTitle",
            parent=base["Normal"],
            fontName=face["semibold"],
            fontSize=7.5,
            leading=10,
            textColor=colors.white,
        ),
        "label": ParagraphStyle(
            "ClaimLabel",
            parent=base["Normal"],
            fontName=face["semibold"],
            fontSize=7,
            leading=9,
            textColor=MUTED,
        ),
        "value": ParagraphStyle(
            "ClaimValue",
            parent=base["Normal"],
            fontName=face["semibold"],
            fontSize=9,
            leading=11.5,
            textColor=INK,
        ),
        "hint": ParagraphStyle(
            "ClaimHint",
            parent=base["Normal"],
            fontName=face["regular"],
            fontSize=7.5,
            leading=10,
            textColor=MUTED,
        ),
        "body": ParagraphStyle(
            "ClaimBody",
            parent=base["Normal"],
            fontName=face["regular"],
            fontSize=9,
            leading=12,
            textColor=INK,
        ),
        "cell": ParagraphStyle(
            "ClaimCell",
            parent=base["Normal"],
            fontName=face["regular"],
            fontSize=8.5,
            leading=11.5,
            textColor=INK,
        ),
        "cell_muted": ParagraphStyle(
            "ClaimCellMuted",
            parent=base["Normal"],
            fontName=face["regular"],
            fontSize=8,
            leading=11,
            textColor=MUTED,
        ),
        "stat_label": ParagraphStyle(
            "ClaimStatLabel",
            parent=base["Normal"],
            fontName=face["semibold"],
            fontSize=7,
            leading=9,
            textColor=MUTED,
        ),
        "stat_value": ParagraphStyle(
            "ClaimStatValue",
            parent=base["Normal"],
            fontName=face["bold"],
            fontSize=11,
            leading=14,
            textColor=INK,
        ),
    }


class _Hairline(Flowable):
    def __init__(self, color: colors.Color = LINE, thickness: float = 0.6) -> None:
        super().__init__()
        self.color = color
        self.thickness = thickness
        self.height = 4

    def draw(self) -> None:
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 2, self.width, 2)


def _card(
    number: str,
    title: str,
    body: list[Any],
    styles: dict[str, ParagraphStyle],
    width: float,
) -> Table:
    header = Table(
        [
            [
                Paragraph(_escape(number), styles["section_n"]),
                Paragraph(_escape(title).upper(), styles["section_title"]),
            ]
        ],
        colWidths=[11 * mm, max(width - 11 * mm, 20 * mm)],
    )
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), GREEN),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, 0), 6),
                ("LEFTPADDING", (1, 0), (1, 0), 1),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ]
        )
    )
    card = Table([[header], [body]], colWidths=[width])
    card.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("BACKGROUND", (0, 1), (-1, 1), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 0),
                ("TOPPADDING", (0, 0), (0, 0), 0),
                ("BOTTOMPADDING", (0, 0), (0, 0), 0),
                ("LEFTPADDING", (0, 1), (0, 1), 7),
                ("RIGHTPADDING", (0, 1), (0, 1), 7),
                ("TOPPADDING", (0, 1), (0, 1), 4),
                ("BOTTOMPADDING", (0, 1), (0, 1), 4),
            ]
        )
    )
    return card


def _pair(left: Any, right: Any, width: float) -> Table:
    gap = 2.2 * mm
    col = (width - gap) / 2
    table = Table([[left, "", right]], colWidths=[col, gap, col])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _block(flowable: Any) -> KeepTogether:
    return KeepTogether([flowable, Spacer(1, 9)])


def _fact_table(
    rows: list[tuple[str, str, str]],
    styles: dict[str, ParagraphStyle],
    width: float,
) -> Table:
    data = []
    for label, value, hint in rows:
        cell = [
            Paragraph(_escape(label).upper(), styles["label"]),
            Paragraph(_escape(value), styles["value"]),
        ]
        if hint:
            cell.append(Paragraph(_escape(hint), styles["hint"]))
        data.append(cell)
    col = width / max(len(data), 1)
    table = Table([data], colWidths=[col] * len(data))
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _kv_table(
    pairs: list[tuple[str, str, str]],
    styles: dict[str, ParagraphStyle],
    width: float,
    columns: int = 2,
) -> Table:
    cells: list[list[Any]] = []
    row: list[Any] = []
    for label, value, hint in pairs:
        block = [
            Paragraph(_escape(label).upper(), styles["label"]),
            Paragraph(_escape(value), styles["value"]),
        ]
        if hint:
            block.append(Paragraph(_escape(hint), styles["hint"]))
        row.append(block)
        if len(row) == columns:
            cells.append(row)
            row = []
    if row:
        while len(row) < columns:
            row.append("")
        cells.append(row)
    if not cells:
        cells = [[""] * columns]
    col = width / columns
    table = Table(cells, colWidths=[col] * columns)
    rules = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if len(cells) > 1:
        rules.append(("LINEBELOW", (0, 0), (-1, -2), 0.35, RULE))
    table.setStyle(TableStyle(rules))
    return table


def _header_table(
    letterhead: dict[str, Any],
    styles: dict[str, ParagraphStyle],
    width: float,
) -> Table:
    logo = _logo_path()
    left: Any
    if logo is not None:
        image = ImageReader(str(logo))
        iw, ih = image.getSize()
        target_w = 40 * mm
        target_h = target_w * (ih / iw) if iw else 12 * mm
        left = Image(str(logo), width=target_w, height=target_h)
        left.hAlign = "LEFT"
    else:
        left = Paragraph("Star Serve", styles["hero_name"])

    agency = _plain(letterhead.get("agency"), "Star Serve")
    legal = _plain(letterhead.get("legal_name"), "")
    contact = _join(letterhead.get("phone"), letterhead.get("email"), sep="  ·  ")
    right = [
        Paragraph("MOTOR CLAIM FILE", styles["doc_title"]),
        Paragraph("Confidential desk copy", styles["doc_sub"]),
    ]
    if agency and agency != "Star Serve":
        right.append(Paragraph(_escape(agency), styles["doc_sub"]))
    elif legal and legal != agency:
        right.append(Paragraph(_escape(legal), styles["doc_sub"]))
    if contact:
        right.append(Paragraph(_escape(contact), styles["doc_sub"]))

    table = Table([[left, right]], colWidths=[width * 0.55, width * 0.45])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ]
        )
    )
    return table


def _hero(payload: dict[str, Any], styles: dict[str, ParagraphStyle], width: float) -> list[Any]:
    claimant = payload.get("claimant") or {}
    financial = payload.get("financial") or {}
    name = _plain(claimant.get("name"), "Unnamed claimant")
    ref = _plain(payload.get("claim_number"), "Claim")
    status = _status_label(payload.get("status"))
    claimed = _money(financial.get("claimed_amount"), financial.get("currency"))
    approved = (
        _money(financial.get("approved_amount"), financial.get("currency"))
        if financial.get("approved_amount") not in (None, "")
        else "—"
    )
    vehicle = payload.get("vehicle") or {}
    policy = payload.get("policy") or {}

    title = Table(
        [
            [
                [
                    Paragraph(_escape(ref), styles["hero_ref"]),
                    Paragraph(_escape(name), styles["hero_name"]),
                ],
                Paragraph(_escape(status), styles["hero_status"]),
            ]
        ],
        colWidths=[width * 0.68, width * 0.32],
    )
    title.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ]
        )
    )

    stats = [
        ("Claimed", claimed, ""),
        ("Approved", approved, ""),
        ("Vehicle", _plain(vehicle.get("registration")), ""),
        ("Policy", _plain(policy.get("policy_number")), ""),
    ]
    stat_cells = []
    for label, value, _hint in stats:
        stat_cells.append(
            [
                Paragraph(_escape(label).upper(), styles["stat_label"]),
                Paragraph(_escape(value), styles["stat_value"]),
            ]
        )
    strip = Table([stat_cells], colWidths=[width / 4] * 4)
    strip.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return [title, Spacer(1, 5), strip]


def _letter_rows(
    payload: dict[str, Any],
    *,
    generated_by: str = "",
    generated_role: str = "",
) -> list[tuple[str, str, str]]:
    rows = [
        ("Agency", _plain(payload.get("agency_name"), "Star Serve"), ""),
        ("Officer", _plain(payload.get("assigned_to_name"), "Unassigned"), ""),
        ("Source", _source_label(payload.get("channel")), ""),
        ("Filed", _day(payload.get("created_at")), ""),
    ]
    if generated_by:
        rows.append(("Generated by", generated_by, generated_role))
    return rows


def _cover_rows(payload: dict[str, Any]) -> list[tuple[str, str, str]]:
    policy = payload.get("policy") or {}
    vehicle = payload.get("vehicle") or {}
    cover = _join(policy.get("product_code"), policy.get("cover_option"))
    period = _join(
        _day(policy.get("cover_start_date")),
        _day(policy.get("cover_end_date")),
        sep=" – ",
    )
    if period == "— – —":
        period = "—"
    vehicle_line = _join(vehicle.get("make"), vehicle.get("model"), vehicle.get("registration"))
    rows = [
        ("Policy", _plain(policy.get("policy_number")), ""),
        ("Cover", cover, ""),
        ("Period", period, ""),
        ("Vehicle", vehicle_line, ""),
    ]
    if vehicle.get("chassis_number"):
        rows.append(("Chassis", _plain(vehicle.get("chassis_number")), ""))
    return rows


def _claimant_rows(payload: dict[str, Any]) -> list[tuple[str, str, str]]:
    claimant = payload.get("claimant") or {}
    return [
        ("Name", _plain(claimant.get("name"), "Unnamed claimant"), ""),
        ("Phone", _plain(claimant.get("phone")), ""),
        ("National ID", _plain(claimant.get("id_number")), ""),
    ]


def _incident_rows(payload: dict[str, Any]) -> list[tuple[str, str, str]]:
    accident = payload.get("accident") or {}
    when = _join(_day(accident.get("incident_date")), _plain(accident.get("incident_time"), ""))
    rows = [
        ("Date", when if when != "—" else _plain(accident.get("incident_date")), ""),
        ("Location", _plain(accident.get("incident_location")), ""),
    ]
    if accident.get("police_abstract_number"):
        rows.append(("Police abstract", _plain(accident.get("police_abstract_number")), ""))
    return rows


def _money_rows(payload: dict[str, Any]) -> list[tuple[str, str, str]]:
    financial = payload.get("financial") or {}
    pay_label, pay_hint = _pay_to(financial.get("beneficiary_type"))
    rows = [
        ("Claimed", _money(financial.get("claimed_amount"), financial.get("currency")), ""),
        (
            "Approved",
            _money(financial.get("approved_amount"), financial.get("currency"))
            if financial.get("approved_amount") not in (None, "")
            else "—",
            "",
        ),
        ("Pay to", pay_label, pay_hint),
    ]
    if financial.get("beneficiary_reference"):
        rows.append(("Payee reference", _plain(financial.get("beneficiary_reference")), ""))
    return rows


def _extra_detail_rows(payload: dict[str, Any]) -> list[tuple[str, str, str]]:
    driver = payload.get("driver") or {}
    damage = payload.get("damage") or {}
    injuries = payload.get("injuries") or {}
    rows: list[tuple[str, str, str]] = []
    if driver.get("name") or driver.get("license_number"):
        rows.append(
            ("Driver", _plain(driver.get("name")), _plain(driver.get("license_number"), ""))
        )
    if damage.get("description"):
        rows.append(("Damage", _plain(damage.get("description")), ""))
    if injuries.get("summary"):
        rows.append(("Injuries", _plain(injuries.get("summary")), ""))
    if injuries.get("medical_notes"):
        rows.append(("Medical notes", _plain(injuries.get("medical_notes")), ""))
    if payload.get("risk_assessment"):
        rows.append(("Risk assessment", _plain(payload.get("risk_assessment")), ""))
    return rows


def _assessment_body(
    payload: dict[str, Any],
    styles: dict[str, ParagraphStyle],
    width: float,
) -> list[Any]:
    vetting = [row for row in (payload.get("vetting") or []) if isinstance(row, dict)]
    if not vetting:
        return [Paragraph("Assessment has not been recorded yet.", styles["body"])]
    latest = next((row for row in vetting if row.get("is_current")), vetting[0])
    decision_key = _plain(latest.get("decision"), "").upper()
    decision = VETTING_DECISIONS.get(decision_key, _pretty(latest.get("decision"), "Started"))
    reason = _plain(latest.get("decision_reason"), "No assessment note on file.")
    parts: list[Any] = [
        Paragraph(f"<b>{_escape(decision)}</b> — {_escape(reason)}", styles["body"]),
        Spacer(1, 3),
    ]
    checklist = latest.get("checklist") if isinstance(latest.get("checklist"), dict) else {}
    checks = [
        (label, "Yes" if checklist.get(key) else "—", "")
        for key, label in VETTING_CHECKS.items()
    ]
    if checks:
        parts.append(_kv_table(checks, styles, width, columns=2))
    return parts


def _approvals_body(payload: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    rows = [
        row
        for row in (payload.get("approvals") or [])
        if isinstance(row, dict) and not row.get("superseded")
    ]
    if not rows:
        return [Paragraph("No agency approval has been recorded yet.", styles["body"])]
    lines = []
    for row in rows:
        decision = _pretty(row.get("decision"))
        reason = _plain(row.get("reason"), "")
        stamp = _when(row.get("created_at"))
        text = f"<b>{_escape(decision)}</b> · {_escape(stamp)}"
        if reason:
            text += f"<br/>{_escape(reason)}"
        lines.append(Paragraph(text, styles["body"]))
        lines.append(Spacer(1, 4))
    return lines


def _insurer_body(
    payload: dict[str, Any],
    styles: dict[str, ParagraphStyle],
    width: float,
) -> list[Any]:
    reviews = [row for row in (payload.get("definite_reviews") or []) if isinstance(row, dict)]
    if not reviews:
        return []
    latest = reviews[0]
    status = _pretty(latest.get("status"))
    decision = _pretty(latest.get("decision")) if latest.get("decision") else "Awaiting decision"
    amount = (
        _money(latest.get("approved_amount"), (payload.get("financial") or {}).get("currency"))
        if latest.get("approved_amount") not in (None, "")
        else "—"
    )
    ref = _plain(latest.get("external_reference"), "—")
    return [
        _kv_table(
            [
                ("Status", status, ""),
                ("Decision", decision, ""),
                ("Insurer amount", amount, ""),
                ("Reference", ref, ""),
            ],
            styles,
            width,
            columns=2,
        )
    ]


def _documents_body(
    payload: dict[str, Any],
    styles: dict[str, ParagraphStyle],
    width: float,
) -> list[Any]:
    docs = [row for row in (payload.get("documents") or []) if isinstance(row, dict)]
    if not docs:
        return [Paragraph("No papers have been uploaded to this file yet.", styles["body"])]
    header = [
        Paragraph("DOCUMENT", styles["label"]),
        Paragraph("KIND", styles["label"]),
        Paragraph("ADDED", styles["label"]),
    ]
    data = [header]
    for doc in docs:
        data.append(
            [
                Paragraph(_escape(doc.get("original_filename")), styles["cell"]),
                Paragraph(_escape(_pretty(doc.get("kind"))), styles["cell"]),
                Paragraph(_escape(_day(doc.get("created_at"))), styles["cell_muted"]),
            ]
        )
    table = Table(data, colWidths=[width * 0.54, width * 0.22, width * 0.24])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SOFT),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return [table]


def _activity_body(
    payload: dict[str, Any],
    styles: dict[str, ParagraphStyle],
    width: float,
) -> list[Any]:
    events = [row for row in (payload.get("timeline") or []) if isinstance(row, dict)]
    if not events:
        return [Paragraph("No activity has been recorded on this file yet.", styles["body"])]
    ordered = sorted(events, key=lambda row: _plain(row.get("created_at"), ""), reverse=False)
    header = [
        Paragraph("WHEN", styles["label"]),
        Paragraph("WHAT HAPPENED", styles["label"]),
        Paragraph("WHO", styles["label"]),
    ]
    data = [header]
    for event in ordered[-24:]:
        title = _activity_title(event)
        when = f"{_day(event.get('created_at'))}  {_clock(event.get('created_at'))}"
        who = event.get("actor_display_name") or _pretty(event.get("actor_type"))
        data.append(
            [
                Paragraph(_escape(when), styles["cell_muted"]),
                Paragraph(_escape(title), styles["cell"]),
                Paragraph(_escape(who), styles["cell"]),
            ]
        )
    table = Table(data, colWidths=[width * 0.28, width * 0.42, width * 0.30])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SOFT),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return [table]


def render_claim_pdf(payload: dict[str, Any], *, letterhead: dict[str, Any] | None = None) -> bytes:
    """Build a multi-page A4 claim file from the same desk payload the UI uses."""
    letterhead = letterhead or {}
    styles = _styles()
    buffer = BytesIO()
    width = A4[0] - 24 * mm
    generated = datetime.now(NAIROBI)
    claim_number = _plain(payload.get("claim_number"), "claim")
    agency = _plain(letterhead.get("agency") or payload.get("agency_name"), "Star Serve")
    generated_by = _plain(letterhead.get("generated_by"), "")
    generated_role = _pretty(letterhead.get("generated_by_role"), "")
    if generated_role in {"—", "Guest"}:
        generated_role = ""
    by_line = f"Generated by {generated_by}" if generated_by else "Generated"
    stamp = f"{generated.day} {generated.strftime('%b %Y, %H:%M')} EAT"

    def _draw_chrome(canvas, doc) -> None:  # type: ignore[no-untyped-def]
        canvas.saveState()
        canvas.setFillColor(GREEN)
        canvas.rect(0, A4[1] - 4, A4[0], 4, stroke=0, fill=1)
        canvas.setFillColor(GREEN_DEEP)
        canvas.rect(0, 0, A4[0], 14 * mm, stroke=0, fill=1)
        canvas.setFillColor(GREEN)
        canvas.rect(0, 14 * mm, A4[0], 1.8, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        face = _fonts()
        canvas.setFont(face["regular"], 7)
        canvas.drawString(
            12 * mm,
            7.6 * mm,
            f"{agency}  ·  Confidential claim file  ·  {claim_number}",
        )
        canvas.setFont(face["regular"], 6.5)
        canvas.drawString(12 * mm, 3.8 * mm, f"{by_line}  ·  {stamp}")
        canvas.drawRightString(A4[0] - 12 * mm, 3.8 * mm, str(doc.page))
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=18 * mm,
        title=f"Star Serve claim file {claim_number}",
        author=generated_by or agency,
        subject="Official motor claim file",
        creator="Star Serve",
    )

    half = (width - 2.2 * mm) / 2
    inner = 14
    next_n = 1

    def take() -> str:
        nonlocal next_n
        label = f"{next_n:02d}"
        next_n += 1
        return label

    story: list[Any] = [
        _header_table(letterhead, styles, width),
        Spacer(1, 4),
        _Hairline(GREEN, 1.2),
        Spacer(1, 5),
        *_hero(payload, styles, width),
        Spacer(1, 8),
        _block(
            _card(
                take(),
                "File",
                [
                    _fact_table(
                        _letter_rows(
                            payload,
                            generated_by=generated_by,
                            generated_role=generated_role,
                        ),
                        styles,
                        width - inner,
                    )
                ],
                styles,
                width,
            )
        ),
        _block(
            _pair(
                _card(
                    take(),
                    "Cover",
                    [_kv_table(_cover_rows(payload), styles, half - inner, columns=1)],
                    styles,
                    half,
                ),
                _card(
                    take(),
                    "Claimant",
                    [_kv_table(_claimant_rows(payload), styles, half - inner, columns=1)],
                    styles,
                    half,
                ),
                width,
            )
        ),
        _block(
            _pair(
                _card(
                    take(),
                    "Incident",
                    [_kv_table(_incident_rows(payload), styles, half - inner, columns=1)],
                    styles,
                    half,
                ),
                _card(
                    take(),
                    "Money",
                    [_kv_table(_money_rows(payload), styles, half - inner, columns=1)],
                    styles,
                    half,
                ),
                width,
            )
        ),
        _block(
            _card(
                take(),
                "What happened",
                [
                    Paragraph(
                        _escape(
                            (payload.get("accident") or {}).get("incident_description")
                            or "No description on file yet."
                        ),
                        styles["body"],
                    )
                ],
                styles,
                width,
            )
        ),
    ]

    extra = _extra_detail_rows(payload)
    if extra:
        story.append(
            _block(
                _card(
                    take(),
                    "Further detail",
                    [_kv_table(extra, styles, width - inner)],
                    styles,
                    width,
                )
            )
        )

    story.append(
        _block(
            _card(
                take(),
                "Assessment",
                _assessment_body(payload, styles, width - inner),
                styles,
                width,
            )
        )
    )
    story.append(
        _block(
            _card(
                take(),
                "Agency decision",
                _approvals_body(payload, styles),
                styles,
                width,
            )
        )
    )

    insurer = _insurer_body(payload, styles, width - inner)
    if insurer:
        story.append(_block(_card(take(), "Insurer", insurer, styles, width)))

    story.extend(
        [
            CondPageBreak(80 * mm),
            _block(
                _card(
                    take(),
                    "Papers on file",
                    _documents_body(payload, styles, width - inner),
                    styles,
                    width,
                )
            ),
            _block(
                _card(
                    take(),
                    "File activity",
                    _activity_body(payload, styles, width - inner),
                    styles,
                    width,
                )
            ),
            Paragraph(
                "This document is generated from the live Star Serve claim file. "
                "It is intended for agency and insurer use and should not be altered.",
                styles["hint"],
            ),
        ]
    )

    doc.build(story, onFirstPage=_draw_chrome, onLaterPages=_draw_chrome)
    return buffer.getvalue()
