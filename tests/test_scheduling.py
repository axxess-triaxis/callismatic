from datetime import datetime, timezone
from unittest.mock import MagicMock

from callismatic import scheduling


def test_propose_slots_text_formats_slots(monkeypatch):
    slots = [
        (datetime(2026, 9, 15, 14, 0, tzinfo=timezone.utc), datetime(2026, 9, 15, 14, 30, tzinfo=timezone.utc)),
        (datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc), datetime(2026, 9, 16, 10, 30, tzinfo=timezone.utc)),
    ]
    monkeypatch.setattr(scheduling, "find_free_slots", lambda duration_minutes, **kw: slots)

    text = scheduling.propose_slots_text(30)

    assert "Tuesday Sep 15 at 2:00 PM" in text
    assert "Wednesday Sep 16 at 10:00 AM" in text


def test_propose_slots_text_handles_no_availability(monkeypatch):
    monkeypatch.setattr(scheduling, "find_free_slots", lambda duration_minutes, **kw: [])

    text = scheduling.propose_slots_text(30)

    assert "no availability" in text.lower()


def test_book_chosen_slot_delegates_to_book_meeting(monkeypatch):
    fake_book_meeting = MagicMock(return_value={"id": "evt-1"})
    monkeypatch.setattr(scheduling, "book_meeting", fake_book_meeting)

    start = datetime(2026, 9, 15, 14, 0, tzinfo=timezone.utc)
    end = datetime(2026, 9, 15, 14, 30, tzinfo=timezone.utc)
    result = scheduling.book_chosen_slot(start, end, "Consultation", "For Daniel Ortiz -- kitchen remodel")

    fake_book_meeting.assert_called_once_with(
        start, end, "Consultation", description="For Daniel Ortiz -- kitchen remodel"
    )
    assert result["id"] == "evt-1"
