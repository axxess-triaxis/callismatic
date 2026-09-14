"""Tests the MCP tool wrappers directly (unit-level, same pattern as test_web.py)
-- demo/mcp_client_test.py is the real, live, over-the-wire proof that the actual
Streamable HTTP transport and protocol handshake work; these tests cover the
tool logic itself without spinning up a server or making a real Bedrock call.
"""

import json
from unittest.mock import MagicMock

from callismatic import mcp_server
from callismatic.schema import CallTriage


def _seed_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "DIGEST_PATH", tmp_path / "digest.json")
    monkeypatch.setattr(mcp_server, "BLOCKLIST_PATH", tmp_path / "blocklist.json")
    monkeypatch.setattr("callismatic.digest_report.DIGEST_PATH", tmp_path / "digest.json")
    monkeypatch.setattr("callismatic.digest_report.BLOCKLIST_PATH", tmp_path / "blocklist.json")
    monkeypatch.setattr("callismatic.todos.TODOS_PATH", tmp_path / "todos.json")
    monkeypatch.setattr("callismatic.tools.DIGEST_PATH", tmp_path / "digest.json")
    monkeypatch.setattr("callismatic.tools.BLOCKLIST_PATH", tmp_path / "blocklist.json")


def test_five_tools_are_registered():
    import asyncio

    tools = asyncio.run(mcp_server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "get_weekly_digest",
        "list_blocked_numbers",
        "list_open_todos",
        "check_caller",
        "triage_message",
    }


def test_get_weekly_digest_wraps_generate_weekly_digest(tmp_path, monkeypatch):
    _seed_paths(tmp_path, monkeypatch)
    summary = mcp_server.get_weekly_digest(days=7)
    assert "Callismatic weekly digest" in summary
    assert "0 voicemail(s)/message(s)" in summary


def test_list_blocked_numbers_returns_most_recent_first(tmp_path, monkeypatch):
    _seed_paths(tmp_path, monkeypatch)
    (tmp_path / "blocklist.json").write_text(
        json.dumps(
            [
                {"phone_number": "+1111111111", "reason": "first", "blocked_at": "2026-01-01T00:00:00Z"},
                {"phone_number": "+2222222222", "reason": "second", "blocked_at": "2026-01-02T00:00:00Z"},
            ]
        ),
        encoding="utf-8",
    )
    result = mcp_server.list_blocked_numbers()
    assert result[0]["phone_number"] == "+2222222222"
    assert result[1]["phone_number"] == "+1111111111"


def test_list_open_todos_wraps_list_todos(tmp_path, monkeypatch):
    _seed_paths(tmp_path, monkeypatch)
    assert mcp_server.list_open_todos() == []


def test_check_caller_reports_no_history_for_unknown_number(tmp_path, monkeypatch):
    _seed_paths(tmp_path, monkeypatch)
    result = mcp_server.check_caller(phone_number="+19998887777")
    assert "No past decisions recorded" in result
    assert "No human corrections mention" in result


def test_triage_message_never_places_a_real_callback(tmp_path, monkeypatch):
    # The whole point of this tool: a voice assistant calling it must never be able
    # to trigger a real outbound CALL-E call as a side effect.
    _seed_paths(tmp_path, monkeypatch)

    triage = CallTriage(
        category="lead",
        summary="Interested in a kitchen remodel.",
        needs_decision=False,
        callback_recommended=True,
        callback_task="Call back to discuss the remodel.",
    )
    fake_agent = MagicMock()
    fake_agent.return_value.structured_output = triage
    monkeypatch.setattr(mcp_server, "_get_agent", lambda: fake_agent)

    fake_route_call = MagicMock(return_value={"status": "completed"})
    monkeypatch.setattr("callismatic.triage.route_call", fake_route_call)

    result = mcp_server.triage_message(text="Interested in a kitchen remodel.", sender="+15550002222")

    assert result["category"] == "lead"
    assert result["callback_recommended"] is True
    fake_route_call.assert_not_called()  # place_callbacks=False is hardcoded in the tool
