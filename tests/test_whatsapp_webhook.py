import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from callismatic.schema import CallTriage
from callismatic.whatsapp_webhook import app, parse_incoming_messages, send_whatsapp_message, verify_signature

SAMPLE_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "WABA_ID",
            "changes": [
                {
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"display_phone_number": "15550001111", "phone_number_id": "PNID"},
                        "contacts": [{"profile": {"name": "Test User"}, "wa_id": "15550002222"}],
                        "messages": [
                            {
                                "from": "15550002222",
                                "id": "wamid.ABC123",
                                "timestamp": "1700000000",
                                "text": {"body": "Please call back to confirm delivery."},
                                "type": "text",
                            }
                        ],
                    },
                    "field": "messages",
                }
            ],
        }
    ],
}

STATUS_ONLY_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "WABA_ID",
            "changes": [{"value": {"statuses": [{"id": "wamid.ABC123", "status": "delivered"}]}, "field": "messages"}],
        }
    ],
}


def test_parse_incoming_messages_extracts_text():
    messages = parse_incoming_messages(SAMPLE_PAYLOAD)
    assert messages == [
        {"sender": "15550002222", "message_id": "wamid.ABC123", "text": "Please call back to confirm delivery."}
    ]


def test_parse_incoming_messages_ignores_status_updates():
    assert parse_incoming_messages(STATUS_ONLY_PAYLOAD) == []


def test_verify_signature_accepts_correct_hmac():
    body = b'{"a": 1}'
    secret = "test-secret"
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_signature(body, signature, secret) is True


def test_verify_signature_rejects_wrong_hmac():
    assert verify_signature(b'{"a": 1}', "sha256=deadbeef", "test-secret") is False


def test_verify_signature_rejects_missing_header():
    assert verify_signature(b"{}", None, "test-secret") is False


def test_get_webhook_verification_succeeds_with_correct_token(monkeypatch):
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "my-verify-token")
    client = TestClient(app)

    response = client.get(
        "/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "my-verify-token", "hub.challenge": "12345"}
    )

    assert response.status_code == 200
    assert response.text == "12345"


def test_get_webhook_verification_fails_with_wrong_token(monkeypatch):
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "my-verify-token")
    client = TestClient(app)

    response = client.get(
        "/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "12345"}
    )

    assert response.status_code == 403


def test_post_webhook_rejects_bad_signature(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "test-secret")
    client = TestClient(app)

    response = client.post("/webhook", json=SAMPLE_PAYLOAD, headers={"X-Hub-Signature-256": "sha256=wrong"})

    assert response.status_code == 403


def test_post_webhook_triages_message_with_valid_signature(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "test-secret")
    import callismatic.whatsapp_webhook as webhook_module

    fake_agent = MagicMock()
    monkeypatch.setattr(webhook_module, "_get_agent", lambda: fake_agent)

    fake_result = MagicMock()
    fake_triage_text_message = MagicMock(return_value=fake_result)
    monkeypatch.setattr(webhook_module, "triage_text_message", fake_triage_text_message)

    body = json.dumps(SAMPLE_PAYLOAD).encode()
    signature = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()

    client = TestClient(app)
    response = client.post("/webhook", content=body, headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"})

    assert response.status_code == 200
    fake_triage_text_message.assert_called_once_with(
        fake_agent, "whatsapp", "15550002222", "wamid.ABC123", "Please call back to confirm delivery."
    )


def test_send_whatsapp_message_requires_credentials(monkeypatch):
    monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
    with pytest.raises(RuntimeError, match="WHATSAPP_ACCESS_TOKEN"):
        send_whatsapp_message("+15550001111", "test")


def test_send_whatsapp_message_surfaces_meta_error_detail(monkeypatch):
    """Confirmed against the real API this session: Meta returns HTTP 400 with a genuinely
    diagnosable error body (e.g. code 131030, recipient not in the test allowlist) -- a bare
    raise_for_status() would discard it and leave only a generic '400 Bad Request'."""
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "PNID")

    fake_response = MagicMock()
    fake_response.status_code = 400
    fake_response.json.return_value = {
        "error": {"message": "(#131030) Recipient phone number not in allowed list", "code": 131030}
    }

    with patch("httpx.post", return_value=fake_response):
        with pytest.raises(RuntimeError, match="131030"):
            send_whatsapp_message("+15550001111", "test")


def test_send_whatsapp_message_success_returns_response_json(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "PNID")

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"messages": [{"id": "wamid.XYZ"}]}

    with patch("httpx.post", return_value=fake_response) as mock_post:
        result = send_whatsapp_message("+15550001111", "hello")

    assert result["messages"][0]["id"] == "wamid.XYZ"
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["to"] == "+15550001111"
    assert kwargs["json"]["text"]["body"] == "hello"
