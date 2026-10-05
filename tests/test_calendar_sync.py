from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from callismatic import calendar_sync


def test_find_free_slots_requires_service_account_file(monkeypatch):
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_FILE", raising=False)
    with pytest.raises(RuntimeError, match="GOOGLE_SERVICE_ACCOUNT_FILE"):
        calendar_sync.find_free_slots(30)


def test_find_free_slots_avoids_busy_periods(monkeypatch):
    now = datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc)  # a real Monday

    fake_service = MagicMock()
    fake_service.freebusy.return_value.query.return_value.execute.return_value = {
        "calendars": {"cal-1": {"busy": [{"start": "2026-09-14T09:00:00+00:00", "end": "2026-09-14T10:00:00+00:00"}]}}
    }
    monkeypatch.setattr(calendar_sync, "_calendar_service", lambda: fake_service)
    monkeypatch.setattr(calendar_sync, "_calendar_id", lambda: "cal-1")

    slots = calendar_sync.find_free_slots(30, days_ahead=1, now=now)

    assert len(slots) > 0
    assert all(start >= datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc) for start, _ in slots)


def test_find_free_slots_skips_weekends(monkeypatch):
    now = datetime(2026, 9, 19, 9, 0, tzinfo=timezone.utc)  # a real Saturday

    fake_service = MagicMock()
    fake_service.freebusy.return_value.query.return_value.execute.return_value = {
        "calendars": {"cal-1": {"busy": []}}
    }
    monkeypatch.setattr(calendar_sync, "_calendar_service", lambda: fake_service)
    monkeypatch.setattr(calendar_sync, "_calendar_id", lambda: "cal-1")

    slots = calendar_sync.find_free_slots(30, days_ahead=2, now=now)  # Sat + Sun only

    assert slots == []


def test_book_meeting_calls_events_insert(monkeypatch):
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {"id": "evt-1"}
    monkeypatch.setattr(calendar_sync, "_calendar_service", lambda: fake_service)
    monkeypatch.setattr(calendar_sync, "_calendar_id", lambda: "cal-1")

    start = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    end = datetime(2026, 9, 14, 10, 30, tzinfo=timezone.utc)
    result = calendar_sync.book_meeting(start, end, "Consultation call")

    assert result["id"] == "evt-1"
    _, kwargs = fake_service.events.return_value.insert.call_args
    assert kwargs["calendarId"] == "cal-1"
    assert kwargs["body"]["summary"] == "Consultation call"


def test_list_upcoming_events_expands_recurring_and_extracts_attendees(monkeypatch):
    now = datetime(2026, 10, 6, 6, 0, tzinfo=timezone.utc)
    fake_service = MagicMock()
    fake_service.events.return_value.list.return_value.execute.return_value = {
        "items": [
            {"id": "e1", "summary": "Partnership call", "start": {"dateTime": "2026-10-06T09:30:00+05:30"},
             "location": "Koramangala, Bengaluru", "attendees": [{"email": "priya@zomato.com"}, {"displayName": "no email"}]},
            {"id": "e2", "start": {"date": "2026-10-07"}},
        ]
    }
    monkeypatch.setattr(calendar_sync, "_calendar_service", lambda: fake_service)
    monkeypatch.setattr(calendar_sync, "_calendar_id", lambda: "cal-1")

    events = calendar_sync.list_upcoming_events(hours_ahead=48, now=now)

    _, kwargs = fake_service.events.return_value.list.call_args
    assert kwargs["singleEvents"] is True and kwargs["orderBy"] == "startTime"
    assert kwargs["timeMax"] == "2026-10-08T06:00:00+00:00"
    assert events[0] == {"id": "e1", "summary": "Partnership call", "start": "2026-10-06T09:30:00+05:30",
                         "location": "Koramangala, Bengaluru", "attendee_emails": ["priya@zomato.com"]}
    assert events[1]["summary"] == "(no title)" and events[1]["start"] == "2026-10-07"
