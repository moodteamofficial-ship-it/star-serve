"""Parse Safaricom Daraja STK callback JSON into a flat verification dict."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def _metadata_items(stk: dict[str, Any]) -> dict[str, Any]:
    meta = stk.get("CallbackMetadata") or {}
    items = meta.get("Item") or []
    out: dict[str, Any] = {}
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("Name") or "").strip()
            if name:
                out[name] = item.get("Value")
    return out


def parse_daraja_stk_callback(payload: dict[str, Any]) -> dict[str, Any]:
    """Return normalized fields for WebhookVerificationResult."""
    body = payload.get("Body") if isinstance(payload.get("Body"), dict) else payload
    stk = body.get("stkCallback") if isinstance(body, dict) else None
    if not isinstance(stk, dict):
        stk = payload.get("stkCallback") if isinstance(payload.get("stkCallback"), dict) else payload

    checkout = str(stk.get("CheckoutRequestID") or stk.get("checkoutRequestID") or "").strip()
    merchant = str(stk.get("MerchantRequestID") or "").strip()
    result_code = stk.get("ResultCode")
    if result_code is None:
        result_code = stk.get("resultCode")
    result_code_str = str(result_code if result_code is not None else "1")
    result_desc = str(stk.get("ResultDesc") or stk.get("resultDesc") or "")

    meta = _metadata_items(stk)
    amount_raw = meta.get("Amount")
    receipt = meta.get("MpesaReceiptNumber") or meta.get("ReceiptNo")
    account_ref = meta.get("AccountReference") or meta.get("BillRefNumber")

    return {
        "CheckoutRequestID": checkout,
        "MerchantRequestID": merchant,
        "ResultCode": result_code_str,
        "ResultDesc": result_desc,
        "Amount": str(amount_raw) if amount_raw is not None else None,
        "MpesaReceiptNumber": str(receipt) if receipt is not None else "",
        "AccountReference": str(account_ref) if account_ref is not None else "",
        "raw_stk": stk,
    }
