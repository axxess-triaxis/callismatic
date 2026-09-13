from unittest.mock import AsyncMock, MagicMock

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
    monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
    if admin_key is not None:
        monkeypatch.setenv("ADMIN_API_KEY", admin_key)
    else:
        monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    return TestClient(web.app)


def test_dashboard_renders_with_no_data(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/")
    assert response.status_code == 200
    assert "Callismatic" in response.text
    assert "No voicemails/messages triaged yet." in response.text


def test_api_digest_and_todos_are_public(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get("/api/digest").status_code == 200
    assert client.get("/api/todos").json() == []
    assert client.get("/api/blocklist").json() == []


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
    assert client.get("/api/todos").json() == []


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
    assert client.get("/api/blocklist").json() == []


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
