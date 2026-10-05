"""Pre-meeting briefs -- SerpApi and the calendar are faked; no key, credits or calendar used."""

from datetime import datetime, timezone

import pytest

from callismatic import briefs

NOW = datetime(2026, 10, 6, 6, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fake_web(monkeypatch):
    monkeypatch.setattr(
        briefs,
        "company_overview",
        lambda company, now=None: {"name": "Zomato", "description": "Indian food delivery company", "website": "zomato.com"}
        if company.lower() == "zomato" else None,
    )
    monkeypatch.setattr(
        briefs,
        "company_news",
        lambda company, n=3, now=None: [{"title": "Zomato posts quarterly results", "source": "Mint", "date": "10/04/2026", "link": "x"}]
        if company.lower() == "zomato" else [],
    )
    monkeypatch.setenv("GOOGLE_CALENDAR_ID", "founder@triaxisventures.com")


def test_organisation_from_attendee_domain_skips_personal_and_own_domains():
    event = {"summary": "Partnership call", "attendee_emails": ["me@gmail.com", "cofounder@triaxisventures.com", "priya@zomato.com"]}
    assert briefs.organisation_for_event(event) == "zomato"
    assert briefs.organisation_for_event({"attendee_emails": ["ops@tcs.co.in"]}) == "tcs"
    assert briefs.organisation_for_event({"attendee_emails": ["a@mail.acme.io"]}) == "acme"


def test_organisation_falls_back_to_with_in_title_and_none_for_personal_events():
    assert briefs.organisation_for_event({"summary": "Call with Acme Logistics", "attendee_emails": []}) == "Acme Logistics"
    assert briefs.organisation_for_event({"summary": "Dentist", "attendee_emails": ["me@gmail.com"]}) is None


def test_brief_contains_overview_news_and_source_note():
    brief = briefs.brief_for_company("Zomato", event={"summary": "Partnership call", "start": "2026-10-06T09:30:00+00:00"})
    assert 'Brief for "Partnership call"' in brief
    assert "About: Zomato -- Indian food delivery company (zomato.com)" in brief
    assert "- Zomato posts quarterly results (Mint, 10/04/2026)" in brief
    assert "verify before quoting" in brief


def test_brief_degrades_gracefully_without_web_results():
    brief = briefs.brief_for_company("Unknown Co")
    assert "no web profile found" in brief and "Recent news: none found." in brief


def test_schedule_briefs_schedules_reminder_before_each_meeting(monkeypatch):
    events = [
        {"id": "e1", "summary": "Partnership call", "start": "2026-10-06T09:30:00+00:00", "location": "", "attendee_emails": ["priya@zomato.com"]},
        {"id": "e2", "summary": "Gym", "start": "2026-10-06T12:00:00+00:00", "location": "", "attendee_emails": []},
    ]
    monkeypatch.setattr("callismatic.calendar_sync.list_upcoming_events", lambda hours_ahead=24, now=None: events)
    scheduled = []
    monkeypatch.setattr("callismatic.reminders.add_reminder", lambda text, due_at, to=None: scheduled.append((text, due_at, to)))

    out = briefs.schedule_briefs(to="+15550009999", now=NOW)

    assert [b["company"] for b in out] == ["zomato"]  # the gym session has nothing to research
    assert scheduled[0][1] == "2026-10-06T09:00:00+00:00"  # 30 min before the meeting
    assert scheduled[0][2] == "+15550009999" and "Zomato posts quarterly results" in scheduled[0][0]


def test_schedule_briefs_dry_run_schedules_nothing_and_never_backdates(monkeypatch):
    soon = [{"id": "e1", "summary": "Call with Zomato", "start": "2026-10-06T06:10:00+00:00", "location": "", "attendee_emails": []}]
    monkeypatch.setattr("callismatic.calendar_sync.list_upcoming_events", lambda hours_ahead=24, now=None: soon)
    scheduled = []
    monkeypatch.setattr("callismatic.reminders.add_reminder", lambda *a, **k: scheduled.append(a))

    out = briefs.schedule_briefs(dry_run=True, now=NOW)

    assert scheduled == []
    assert out[0]["due_at"] == NOW.isoformat()  # meeting is 10 min away: deliver now, not in the past
