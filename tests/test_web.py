from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from callismatic import web
from callismatic.schema import CallTriage


def _client(tmp_path, monkeypatch, *, admin_key: str | None = "test-admin-key"):
    monkeypatch.setattr(web, "DIGEST_PATH", tmp_path / "digest.json")
    monkeypatch.setattr(web, "BLOCKLIST_PATH", tmp_path / "blocklist.json")
    monkeypatch.setattr("callismatic.todos.TODOS_PATH", tmp_path / "todos.json")
    monkeypatch.setattr("callismatic.tools.DIGEST_PATH", tmp_path / "digest.json")
    monkeypatch.setattr("callismatic.tools.BLOCKLIST_PATH", tmp_path / "blocklist.json")
    monkeypatch.setattr("callismatic.digest_report.DIGEST_PATH", tmp_path / "digest.json")
    monkeypatch.setattr("callismatic.digest_report.BLOCKLIST_PATH", tmp_path / "blocklist.json")
    # Without this, /api/reminders/send processed the developer's real outputs/reminders.json
    # and attempted real WhatsApp deliveries during tests (found 2026-10-05: it only failed
    # because the local WhatsApp token had expired). Isolate the store AND remove the
    # credentials, so no test can message a real person even if a path is missed.
    monkeypatch.setattr("callismatic.reminders.REMINDERS_PATH", tmp_path / "reminders.json")
    monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
    monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
    monkeypatch.delenv("READ_API_KEY", raising=False)
    if admin_key is not None:
        monkeypatch.setenv("ADMIN_API_KEY", admin_key)
    else:
        monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    return TestClient(web.app)


def test_dashboard_needs_a_read_key(tmp_path, monkeypatch):
    # The dashboard lists senders' phone numbers and message summaries, so it is never public
    # (GTM 2026-11-13, before the verified WhatsApp number goes live). A read key works.
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setenv("READ_API_KEY", "test-read-key")
    assert client.get("/").status_code == 401
    assert client.get("/", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/", headers={"X-API-Key": "test-read-key"}).status_code == 200


def test_dashboard_fails_closed_with_no_keys_configured(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, admin_key=None)
    assert client.get("/").status_code == 401

def test_dashboard_renders_with_no_data(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/", headers={"X-API-Key": "test-admin-key"})
    assert response.status_code == 200
    assert "Callismatic" in response.text
    assert "No voicemails/messages triaged yet." in response.text


ADMIN = {"X-API-Key": "test-admin-key"}
READ_ROUTES = ("/api/digest", "/api/todos", "/api/blocklist")


def test_read_api_rejects_missing_or_wrong_key(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    for route in READ_ROUTES:
        assert client.get(route).status_code == 401, route
        assert client.get(route, headers={"X-API-Key": "wrong"}).status_code == 401, route


def test_read_api_accepts_read_key_or_admin_key(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setenv("READ_API_KEY", "test-read-key")
    for headers in ({"X-API-Key": "test-read-key"}, ADMIN):
        assert client.get("/api/digest", headers=headers).status_code == 200
        assert client.get("/api/todos", headers=headers).json() == []
        assert client.get("/api/blocklist", headers=headers).json() == []


def test_read_api_fails_closed_when_no_key_is_configured(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, admin_key=None)
    for route in READ_ROUTES:
        assert client.get(route).status_code == 401, route
        assert client.get(route, headers={"X-API-Key": ""}).status_code == 401, route


def test_read_key_cannot_call_mutating_endpoints(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setenv("READ_API_KEY", "test-read-key")
    response = client.post("/api/reminders/send", headers={"X-API-Key": "test-read-key"})
    assert response.status_code == 401


def test_mutating_endpoint_rejects_missing_api_key(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post("/api/reminders/send")
    assert response.status_code == 401


def test_mutating_endpoint_rejects_wrong_api_key(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post("/api/reminders/send", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_mutating_endpoint_accepts_correct_api_key(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post("/api/reminders/send", headers={"X-API-Key": "test-admin-key"})
    assert response.status_code == 200
    assert response.json() == {"sent_count": 0, "sent": []}


def test_complete_todo_via_api(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    from callismatic.todos import add_todo

    item = add_todo("Call the lead back.")

    response = client.post(f"/api/todos/{item['id']}/complete", headers={"X-API-Key": "test-admin-key"})
    assert response.status_code == 200
    assert client.get("/api/todos", headers=ADMIN).json() == []


def test_add_reminder_via_api(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post(
        "/api/reminders",
        json={"text": "Follow up", "due_at": "2026-09-20T00:00:00+00:00", "to": "+15550001111"},
        headers={"X-API-Key": "test-admin-key"},
    )
    assert response.status_code == 200
    assert response.json()["text"] == "Follow up"


def test_unblock_via_api(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    from callismatic.tools import block_number

    block_number("+15550001111", "scam")

    response = client.post(
        "/api/correct/unblock", json={"phone_number": "+15550001111"}, headers={"X-API-Key": "test-admin-key"}
    )
    assert response.status_code == 200
    assert response.json()["was_on_blocklist"] is True
    assert client.get("/api/blocklist", headers=ADMIN).json() == []


def test_triage_text_via_api(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    triage = CallTriage(category="routine", summary="ok", needs_decision=False)
    fake_response = MagicMock()
    fake_response.structured_output = triage
    fake_agent = MagicMock()
    fake_agent.invoke_async = AsyncMock(return_value=fake_response)
    fake_agent.return_value = fake_response
    monkeypatch.setattr(web, "_get_agent", lambda: fake_agent)

    response = client.post(
        "/api/triage/text",
        json={"channel": "sms", "sender": "+15550001111", "message_id": "msg-1", "text": "hello"},
        headers={"X-API-Key": "test-admin-key"},
    )
    assert response.status_code == 200
    assert response.json()["triage"]["category"] == "routine"


def test_whatsapp_verify_endpoint(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "my-token")
    response = client.get(
        "/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "my-token", "hub.challenge": "xyz"}
    )
    assert response.status_code == 200
    assert response.text == "xyz"


def test_whatsapp_verify_endpoint_rejects_wrong_token(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "my-token")
    response = client.get(
        "/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "my-tokem", "hub.challenge": "xyz"}
    )
    assert response.status_code == 403


def test_whatsapp_webhook_fails_closed_without_app_secret(tmp_path, monkeypatch):
    # Without a secret there's no way to tell Meta from a forger, so nothing may be triaged.
    client = _client(tmp_path, monkeypatch)
    monkeypatch.delenv("WHATSAPP_APP_SECRET", raising=False)
    get_agent = MagicMock()
    monkeypatch.setattr(web, "_get_agent", get_agent)
    triage = MagicMock()
    monkeypatch.setattr(web, "triage_text_message", triage)

    response = client.post("/webhook", json={"object": "whatsapp_business_account", "entry": []})

    assert response.status_code == 503
    get_agent.assert_not_called()
    triage.assert_not_called()



def test_signed_whatsapp_message_is_triaged_without_a_callback(tmp_path, monkeypatch):
    # A WhatsApp message can come from anyone. It becomes a triaged lead (and, through STILL,
    # an AXXESS task) but must never trigger a real phone call back to someone who did not
    # ask for one (GTM 2026-11-13: calling rules in India and the UAE).
    import hashlib
    import hmac
    import json

    client = _client(tmp_path, monkeypatch)
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "test-secret")
    monkeypatch.setattr(web, "_get_agent", lambda: MagicMock())
    triage = MagicMock()
    monkeypatch.setattr(web, "triage_text_message", triage)
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"messages": [
            {"from": "919800000000", "id": "wamid.TEST", "type": "text", "text": {"body": "Interested in a demo"}}
        ]}}]}],
    }
    body = json.dumps(payload).encode("utf-8")
    signature = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()

    response = client.post(
        "/webhook", content=body, headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"}
    )

    assert response.status_code == 200
    triage.assert_called_once()
    args, kwargs = triage.call_args
    assert args[1:] == ("whatsapp", "919800000000", "wamid.TEST", "Interested in a demo")
    assert kwargs.get("place_callbacks") is False

MCP_INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def mcp_client():
    # One client for every /mcp test: web._lifespan starts the MCP session manager once per
    # process (deliberately, for Lambda), bound to the event loop of the first client that
    # runs the lifespan.
    with TestClient(web.app, base_url="http://localhost:8000") as client:
        yield client


@pytest.fixture
def mcp_keys(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("READ_API_KEY", "test-read-key")


def test_mcp_rejects_requests_without_a_key(mcp_client, mcp_keys):
    assert mcp_client.post("/mcp", json=MCP_INIT, headers=MCP_HEADERS).status_code == 401
    bad = {**MCP_HEADERS, "Authorization": "Bearer wrong"}
    assert mcp_client.post("/mcp", json=MCP_INIT, headers=bad).status_code == 401


def test_mcp_accepts_read_key_as_header_or_bearer(mcp_client, mcp_keys):
    for auth in ({"X-API-Key": "test-read-key"}, {"Authorization": "Bearer test-read-key"}):
        response = mcp_client.post("/mcp", json=MCP_INIT, headers={**MCP_HEADERS, **auth})
        assert response.status_code == 200, response.text
        assert response.json()["result"]["serverInfo"]["name"] == "callismatic"


def test_mcp_rejects_unknown_host_and_origin(mcp_client, mcp_keys):
    # DNS-rebinding protection: a valid key is not enough from a Host or Origin not on the list.
    evil_host = {**MCP_HEADERS, **ADMIN, "Host": "evil.example"}
    assert mcp_client.post("/mcp", json=MCP_INIT, headers=evil_host).status_code == 421
    evil_origin = {**MCP_HEADERS, **ADMIN, "Origin": "https://evil.example"}
    assert mcp_client.post("/mcp", json=MCP_INIT, headers=evil_origin).status_code == 403
    deployed = {**MCP_HEADERS, **ADMIN, "Host": "awpfsufk4dofdncv6cgqsaifwy0kvolm.lambda-url.us-east-1.on.aws"}
    assert mcp_client.post("/mcp", json=MCP_INIT, headers=deployed).status_code == 200
