from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from callismatic import reminders


def test_add_and_due_reminders(tmp_path, monkeypatch):
    monkeypatch.setattr(reminders, "REMINDERS_PATH", tmp_path / "reminders.json")

    now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    reminders.add_reminder("Call the lead back", (now - timedelta(hours=1)).isoformat(), to="+15550001111")
    reminders.add_reminder("Follow up next week", (now + timedelta(days=7)).isoformat())

    due = reminders.due_reminders(now=now)

    assert len(due) == 1
    assert due[0]["text"] == "Call the lead back"


def test_send_due_reminders_delivers_via_whatsapp(tmp_path, monkeypatch):
    monkeypatch.setattr(reminders, "REMINDERS_PATH", tmp_path / "reminders.json")

    now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    reminders.add_reminder("Call the lead back", (now - timedelta(hours=1)).isoformat(), to="+15550001111")

    fake_send = MagicMock()
    monkeypatch.setattr("callismatic.whatsapp_webhook.send_whatsapp_message", fake_send)

    sent = reminders.send_due_reminders(now=now)

    assert len(sent) == 1
    fake_send.assert_called_once_with("+15550001111", "Reminder: Call the lead back")
    assert reminders.due_reminders(now=now) == []  # marked sent, no longer due


def test_send_due_reminders_falls_back_to_stdout_on_delivery_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(reminders, "REMINDERS_PATH", tmp_path / "reminders.json")

    now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    reminders.add_reminder("Call the lead back", (now - timedelta(hours=1)).isoformat(), to="+15550001111")

    monkeypatch.setattr(
        "callismatic.whatsapp_webhook.send_whatsapp_message",
        MagicMock(side_effect=RuntimeError("WHATSAPP_ACCESS_TOKEN is not set")),
    )

    sent = reminders.send_due_reminders(now=now)

    assert len(sent) == 1
    assert "Reminder: Call the lead back" in capsys.readouterr().out


def test_send_due_reminders_without_recipient_prints_only(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(reminders, "REMINDERS_PATH", tmp_path / "reminders.json")

    now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    reminders.add_reminder("Internal note", (now - timedelta(hours=1)).isoformat())

    sent = reminders.send_due_reminders(now=now)

    assert len(sent) == 1
    assert "Reminder: Internal note" in capsys.readouterr().out
