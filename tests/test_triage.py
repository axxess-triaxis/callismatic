from pathlib import Path
from unittest.mock import MagicMock

from callismatic.schema import CallTriage
from callismatic.triage import caller_number_from_filename, triage_text_message


def test_extracts_phone_number_from_filename():
    assert caller_number_from_filename(Path("scam_gift_card_+15550001111.wav")) == "+15550001111"


def test_missing_phone_number_returns_unknown():
    assert caller_number_from_filename(Path("no_number_here.wav")) == "unknown"


def test_triage_text_message_routes_through_shared_pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr("callismatic.tools.DIGEST_PATH", tmp_path / "digest.json")
    monkeypatch.setattr("callismatic.tools.BLOCKLIST_PATH", tmp_path / "blocklist.json")

    fake_route_call = MagicMock(return_value={"status": "completed"})
    monkeypatch.setattr("callismatic.triage.route_call", fake_route_call)

    triage = CallTriage(
        category="routine",
        summary="Confirming a delivery window.",
        needs_decision=False,
        callback_recommended=True,
        callback_task="Call back to confirm the delivery window.",
    )
    fake_agent = MagicMock()
    fake_agent.return_value.structured_output = triage

    result = triage_text_message(
        fake_agent, "whatsapp", "+15550001111", "msg-1", "Please call back to confirm delivery."
    )

    assert result.file_name == "whatsapp:msg-1"
    assert result.caller_number == "+15550001111"
    fake_route_call.assert_called_once_with("Call back to confirm the delivery window.", "+15550001111")
    assert result.callback_result == {"status": "completed"}


def test_triage_text_message_skips_callback_when_not_recommended(tmp_path, monkeypatch):
    monkeypatch.setattr("callismatic.tools.DIGEST_PATH", tmp_path / "digest.json")
    monkeypatch.setattr("callismatic.tools.BLOCKLIST_PATH", tmp_path / "blocklist.json")

    fake_route_call = MagicMock()
    monkeypatch.setattr("callismatic.triage.route_call", fake_route_call)

    triage = CallTriage(
        category="important",
        summary="A client dispute needing a human.",
        needs_decision=True,
        callback_recommended=False,
    )
    fake_agent = MagicMock()
    fake_agent.return_value.structured_output = triage

    result = triage_text_message(fake_agent, "sms", "+15550002222", "msg-2", "We need to talk about the contract.")

    fake_route_call.assert_not_called()
    assert result.callback_result is None
    assert result.triage.needs_decision is True


def test_crm_sync_failure_does_not_break_triage(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("callismatic.tools.DIGEST_PATH", tmp_path / "digest.json")
    monkeypatch.setattr("callismatic.tools.BLOCKLIST_PATH", tmp_path / "blocklist.json")
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet-123")
    monkeypatch.setattr(
        "callismatic.crm_sheets.sync_lead_to_sheet",
        MagicMock(side_effect=RuntimeError("Sheets API is down")),
    )

    triage = CallTriage(category="routine", summary="Nothing urgent.", needs_decision=False)
    fake_agent = MagicMock()
    fake_agent.return_value.structured_output = triage

    result = triage_text_message(fake_agent, "sms", "+15550003333", "msg-3", "Just checking in.")

    assert result.error is None
    assert "CRM sync" in capsys.readouterr().err
