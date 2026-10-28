"""Daraja STK callback parsing."""

from app.integrations.payments.mpesa.callback_parse import parse_daraja_stk_callback


def test_parse_daraja_success_callback() -> None:
    payload = {
        "Body": {
            "stkCallback": {
                "MerchantRequestID": "mr-1",
                "CheckoutRequestID": "ws_CO_123",
                "ResultCode": 0,
                "ResultDesc": "The service request is processed successfully.",
                "CallbackMetadata": {
                    "Item": [
                        {"Name": "Amount", "Value": 1500},
                        {"Name": "MpesaReceiptNumber", "Value": "QAB123"},
                        {"Name": "PhoneNumber", "Value": 254712345678},
                        {"Name": "AccountReference", "Value": "PAY-ABC"},
                    ]
                },
            }
        }
    }
    flat = parse_daraja_stk_callback(payload)
    assert flat["CheckoutRequestID"] == "ws_CO_123"
    assert flat["ResultCode"] == "0"
    assert flat["Amount"] == "1500"
    assert flat["MpesaReceiptNumber"] == "QAB123"
    assert flat["AccountReference"] == "PAY-ABC"
