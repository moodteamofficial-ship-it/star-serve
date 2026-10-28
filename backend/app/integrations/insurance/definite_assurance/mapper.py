"""Map Definite Assurance payloads → Star Serve domain shapes."""

from typing import Any


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def classify_client_lookup(payload: Any) -> str:
    """FOUND / ABSENT / UNKNOWN — guests must never treat UNKNOWN as new."""
    if payload is None or payload == "" or payload is False:
        return "ABSENT"
    if isinstance(payload, list):
        if not payload:
            return "ABSENT"
        if any(isinstance(item, dict) for item in payload):
            return "FOUND" if map_client({"data": payload}) else "UNKNOWN"
        return "UNKNOWN"
    if not isinstance(payload, dict):
        return "UNKNOWN"
    if payload in ({}, {"data": None}, {"data": {}}, {"data": []}):
        return "ABSENT"
    data = payload.get("data", payload)
    if data in (None, {}, []):
        message = str(payload.get("message") or payload.get("Message") or "").lower()
        if "not found" in message or "no client" in message or "does not exist" in message:
            return "ABSENT"
        if payload.get("success") is False or payload.get("found") is False:
            return "ABSENT"
        if len(payload) <= 2 and not any(
            key in payload for key in ("OID", "ClientOID", "idNumber", "IDNumber", "clients")
        ):
            return "ABSENT"
    mapped = map_client(payload)
    if mapped is not None:
        return "FOUND"
    for nest in ("clients", "Clients"):
        raw = payload.get(nest)
        if isinstance(raw, list) and raw:
            if any(isinstance(item, dict) and map_client(item) for item in raw):
                return "FOUND"
            return "UNKNOWN"
    message = str(payload.get("message") or payload.get("Message") or "").lower()
    if "not found" in message or "no client" in message or "does not exist" in message:
        return "ABSENT"
    if payload.get("success") is False:
        return "ABSENT"
    return "UNKNOWN"


def map_client(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    if isinstance(data, list) and data:
        data = data[0] if isinstance(data[0], dict) else {}
    if not isinstance(data, dict):
        return None
    # Nested createClient / checkClient shapes
    for nest_key in ("client", "Client", "clientDetails"):
        nested = data.get(nest_key)
        if isinstance(nested, dict):
            data = {**data, **nested}
            break
    id_number = _first(data.get("idNumber"), data.get("IDNumber"), data.get("id_number"))
    oid = _first(
        data.get("OID"),
        data.get("ClientOID"),
        data.get("clientOID"),
        data.get("clientId"),
        data.get("ClientId"),
        data.get("id"),
    )
    if not id_number and not oid and not _first(data.get("firstName"), data.get("name")):
        # Some createClient responses are { success, message, clientOID }
        oid = _first(payload.get("clientOID"), payload.get("OID"), payload.get("ClientOID")) if isinstance(payload, dict) else None
        if not oid:
            return None
    return {
        "external_ref": str(oid or id_number),
        "first_name": _first(data.get("firstName"), data.get("FirstName"), ""),
        "last_name": _first(data.get("lastName"), data.get("LastName"), ""),
        "other_names": _first(data.get("otherNames"), data.get("OtherNames")),
        "id_number": str(id_number) if id_number else None,
        "kra_pin": _first(data.get("pin"), data.get("PIN"), data.get("kraPin")),
        "phone": _first(data.get("phone"), data.get("Phone"), data.get("mobile")),
        "email": _first(data.get("email"), data.get("Email")),
        "raw_keys": sorted(data.keys()),
    }


def map_intermediary(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        return None
    identification = _first(
        data.get("identification"), data.get("Identification"), data.get("idNumber")
    )
    name = _first(data.get("name"), data.get("Name"))
    if not identification and not name:
        return None
    return {
        "external_ref": str(
            _first(data.get("intermediaryId"), data.get("id"), identification)
        ),
        "name": name or "",
        "email": _first(data.get("email"), data.get("Email")),
        "phone": _first(data.get("phone"), data.get("Phone")),
        "identification": str(identification) if identification else None,
        "kra_pin": _first(data.get("krapin"), data.get("kraPin"), data.get("pin")),
        "raw_keys": sorted(data.keys()),
    }


def map_products(payload: Any) -> list[dict[str, Any]]:
    rows = _as_list(payload)
    mapped: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        # Live/UAT shape: { product: { ProductOID, ProductDescription }, coverOptions: [...] }
        product = item.get("product") if isinstance(item.get("product"), dict) else item
        cover_raw = (
            item.get("coverOptions")
            or item.get("cover_options")
            or item.get("CoverOptions")
            or item.get("covers")
            or product.get("coverOptions")
            or []
        )
        external_id = _first(
            product.get("ProductOID"),
            product.get("OID"),
            product.get("oid"),
            product.get("id"),
            product.get("productId"),
            product.get("ProductId"),
            product.get("code"),
            product.get("productCode"),
            item.get("OID"),
            item.get("id"),
        )
        name = _first(
            product.get("ProductDescription"),
            product.get("name"),
            product.get("productName"),
            product.get("ProductName"),
            product.get("Name"),
            item.get("name"),
            external_id,
        )
        if not external_id or not name:
            continue
        raw_category = _first(
            product.get("category"),
            product.get("Category"),
            product.get("productCategory"),
            product.get("ProductCategory"),
            product.get("class"),
            product.get("Class"),
            item.get("category"),
        )
        category = _normalize_category(str(raw_category) if raw_category else None, str(name))
        cover_options = _map_cover_options(cover_raw)
        mapped.append(
            {
                "external_id": str(external_id),
                "code": str(
                    _first(product.get("code"), product.get("productCode"), external_id)
                ).upper(),
                "name": str(name),
                "description": _first(
                    product.get("description"), product.get("desc"), product.get("Narration")
                ),
                "category": category,
                "cover_options": cover_options,
                "provider_code": "DEFINITE_ASSURANCE",
            }
        )
    return mapped


def map_makes(payload: Any) -> list[dict[str, Any]]:
    rows = _as_list(payload)
    mapped: list[dict[str, Any]] = []
    for idx, item in enumerate(rows):
        if isinstance(item, str):
            mapped.append(
                {
                    "external_id": item,
                    "code": item.upper().replace(" ", "_"),
                    "name": item,
                    "sort_order": (idx + 1) * 10,
                    "models": [],
                    "provider_code": "DEFINITE_ASSURANCE",
                }
            )
            continue
        if not isinstance(item, dict):
            continue
        # Live/UAT shape: { make: { MakeOID, Make }, models: [{ ModelOID, Model }] }
        make = item.get("make") if isinstance(item.get("make"), dict) else item
        external_id = _first(
            make.get("MakeOID"),
            make.get("OID"),
            make.get("MakeCode"),
            make.get("makeCode"),
            make.get("code"),
            make.get("id"),
            make.get("name"),
            item.get("OID"),
            item.get("id"),
        )
        name = _first(
            make.get("Make"),
            make.get("name"),
            make.get("make"),
            item.get("name"),
            external_id,
        )
        if not external_id or not name:
            continue
        models_raw = item.get("models") or item.get("Models") or item.get("modelCodes") or []
        models: list[dict[str, str]] = []
        if isinstance(models_raw, list):
            for m in models_raw:
                if isinstance(m, dict):
                    mid = _first(
                        m.get("ModelOID"),
                        m.get("OID"),
                        m.get("ModelCode"),
                        m.get("id"),
                        m.get("code"),
                    )
                    mname = _first(m.get("Model"), m.get("name"), m.get("ModelName"), mid)
                    if mid and mname:
                        models.append({"id": str(mid), "name": str(mname).strip()})
                elif m is not None:
                    models.append({"id": str(m), "name": str(m)})
        mapped.append(
            {
                "external_id": str(external_id),
                "code": str(external_id).upper().replace(" ", "_"),
                "name": str(name).strip(),
                "sort_order": int(_first(item.get("sortOrder"), (idx + 1) * 10)),
                "models": models,
                "provider_code": "DEFINITE_ASSURANCE",
            }
        )
    return mapped


def _map_cover_options(cover_raw: Any) -> list[dict[str, str]]:
    if isinstance(cover_raw, str):
        return [{"id": c.strip(), "name": c.strip()} for c in cover_raw.split(",") if c.strip()]
    if not isinstance(cover_raw, list):
        return []
    out: list[dict[str, str]] = []
    for c in cover_raw:
        if isinstance(c, dict):
            cid = _first(
                c.get("CoverOptionOID"),
                c.get("OID"),
                c.get("id"),
                c.get("code"),
                c.get("coverOption"),
                c.get("name"),
            )
            cname = _first(
                c.get("CoverOption"),
                c.get("name"),
                c.get("label"),
                cid,
            )
            if cid and cname:
                out.append({"id": str(cid), "name": str(cname)})
        elif c is not None:
            out.append({"id": str(c), "name": str(c)})
    return out


# Canonical quote-wizard classes (no catch-all "Motor").
_CANONICAL_CATEGORIES = frozenset(
    {
        "Motor PSV",
        "Cars",
        "Motorcycle",
        "Tuk Tuk",
        "Motor Commercial",
        "Private Hire",
    }
)


def _normalize_category(raw: str | None, name: str) -> str:
    """Map provider/raw labels into the Definite motor classes."""
    if raw:
        cleaned = " ".join(str(raw).split())
        for known in _CANONICAL_CATEGORIES:
            if cleaned.casefold() == known.casefold():
                return known
        # Provider sometimes sends a loose "Motor" — re-classify from the name.
        if cleaned.casefold() not in {"motor", "other", "general"}:
            inferred = _category_from_name(cleaned)
            if inferred in _CANONICAL_CATEGORIES:
                return inferred
    return _category_from_name(name)


def _category_from_name(name: str) -> str:
    upper = " ".join(name.upper().split())
    # Word-ish tokens so "CARTAGE" does not match "CAR".
    tokens = set(upper.replace("-", " ").replace("(", " ").replace(")", " ").replace(",", " ").split())

    if "PRIVATE HIRE" in upper or "UBER" in upper or "CHAUFFER" in upper or "CHAUFFEUR" in upper:
        return "Private Hire"
    if (
        "MOTOR CYCLE" in upper
        or "MOTORCYCLE" in upper
        or "BIKE" in tokens
        or "BODA" in tokens
    ):
        return "Motorcycle"
    # Definite exposes TUK TUK PSV / TUK TUK COMMERCIAL as distinct products.
    if "TUK" in tokens or "TUKTUK" in tokens:
        return "Tuk Tuk"
    if "PSV" in tokens or "MATATU" in tokens:
        return "Motor PSV"
    if (
        "COMMERCIAL" in upper
        or "COMMERICIAL" in upper  # live Definite typo
        or "COMM" in tokens
        or "TRUCK" in tokens
        or "LORRY" in tokens
        or "CARTAGE" in tokens
        or "AGRICULTURAL" in tokens
        or {"OWN", "GOODS"} <= tokens
    ):
        return "Motor Commercial"
    if (
        "MOTOR PRIVATE" in upper
        or "PRIVATE CAR" in upper
        or "PRIVATE" in tokens
        or "SALOON" in tokens
        or "CARS" in tokens
        or tokens & {"CAR", "SUV", "SALOON"}
    ):
        return "Cars"
    # Default remaining motor lines into Cars — never expose a bare "Motor" class.
    return "Cars"


def map_cancellation_reasons(payload: Any) -> list[dict[str, Any]]:
    rows = _as_list(payload)
    mapped: list[dict[str, Any]] = []
    for item in rows:
        if isinstance(item, str):
            mapped.append(
                {
                    "code": item.upper().replace(" ", "_")[:64],
                    "label": item,
                    "provider_code": "DEFINITE_ASSURANCE",
                }
            )
            continue
        if not isinstance(item, dict):
            continue
        code = _first(item.get("code"), item.get("reasonCode"), item.get("id"), item.get("name"))
        label = _first(item.get("label"), item.get("name"), item.get("reason"), code)
        if not code or not label:
            continue
        mapped.append(
            {
                "code": str(code).upper().replace(" ", "_")[:64],
                "label": str(label),
                "provider_code": "DEFINITE_ASSURANCE",
            }
        )
    return mapped


def map_premium(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        data = {}
    # Definite sometimes returns {"premium": false} for unsupported combos
    if data.get("premium") is False:
        return {
            "basic_premium": None,
            "phcf": None,
            "training_levy": None,
            "stamp_duty": None,
            "gross_premium": None,
        }
    return {
        "basic_premium": _num(
            _first(data.get("basicPremium"), data.get("BasicPremium"), data.get("basic_premium"))
        ),
        "phcf": _num(_first(data.get("PHCF"), data.get("phcf"))),
        "training_levy": _num(
            _first(data.get("trainingLevy"), data.get("TrainingLevy"), data.get("training_levy"))
        ),
        "stamp_duty": _num(
            _first(data.get("stampDuty"), data.get("StampDuty"), data.get("stamp_duty"))
        ),
        "gross_premium": _num(
            _first(data.get("grossPremium"), data.get("GrossPremium"), data.get("gross_premium"))
        ),
    }


def _as_list(payload: Any) -> list[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "items", "results", "products", "makes", "reasons"):
            if isinstance(payload.get(key), list):
                return payload[key]
        return [payload]
    return []


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
