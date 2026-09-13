"""Google Calendar access via the same service account already used for
Google Sheets CRM sync (crm_sheets.py) -- Calendar, unlike Google Tasks,
supports sharing a specific resource with any email address (including a
service account's), so no new OAuth flow is needed. You share ONE calendar
with GOOGLE_SERVICE_ACCOUNT_FILE's `client_email` (Settings and sharing ->
Share with specific people -> add that email -> "Make changes to events"),
same pattern as sharing the Sheet.

Needs GOOGLE_SERVICE_ACCOUNT_FILE (already required for crm_sheets.py) and
GOOGLE_CALENDAR_ID (the calendar's ID -- for a personal calendar this is
usually just the owning Gmail address; for a secondary calendar it's under
Settings -> Integrate calendar -> Calendar ID).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

JsonObject = dict[str, Any]


def _calendar_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    key_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    if not key_file:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_FILE is not set -- see README.md for setup.")
    credentials = service_account.Credentials.from_service_account_file(
        key_file, scopes=["https://www.googleapis.com/auth/calendar"]
    )
    return build("calendar", "v3", credentials=credentials)


def _calendar_id() -> str:
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID")
    if not calendar_id:
        raise RuntimeError("GOOGLE_CALENDAR_ID is not set -- see README.md for setup.")
    return calendar_id


def find_free_slots(
    duration_minutes: int,
    *,
    days_ahead: int = 7,
    business_hours: tuple[int, int] = (9, 17),
    now: datetime | None = None,
) -> list[tuple[datetime, datetime]]:
    """Returns a list of (start, end) UTC datetime tuples where a `duration_minutes` meeting
    could be booked, within business_hours (local-hour numbers, e.g. 9-17) on each of the
    next `days_ahead` days, using the calendar's real freebusy data.

    This does not book anything -- it only reads. Weekends are skipped entirely.
    """
    now = now or datetime.now(timezone.utc)
    window_end = now + timedelta(days=days_ahead)

    service = _calendar_service()
    calendar_id = _calendar_id()
    freebusy = (
        service.freebusy()
        .query(body={"timeMin": now.isoformat(), "timeMax": window_end.isoformat(), "items": [{"id": calendar_id}]})
        .execute()
    )
    busy_periods = [
        (datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"]))
        for b in freebusy["calendars"][calendar_id]["busy"]
    ]

    slots: list[tuple[datetime, datetime]] = []
    duration = timedelta(minutes=duration_minutes)
    day_cursor = now.date()
    for _ in range(days_ahead):
        if day_cursor.weekday() < 5:  # Monday=0 .. Friday=4
            day_start = datetime.combine(day_cursor, datetime.min.time(), tzinfo=timezone.utc).replace(
                hour=business_hours[0]
            )
            day_end = datetime.combine(day_cursor, datetime.min.time(), tzinfo=timezone.utc).replace(
                hour=business_hours[1]
            )
            cursor = max(day_start, now)
            while cursor + duration <= day_end:
                candidate_end = cursor + duration
                overlaps = any(candidate_end > b_start and cursor < b_end for b_start, b_end in busy_periods)
                if not overlaps:
                    slots.append((cursor, candidate_end))
                cursor += duration
        day_cursor += timedelta(days=1)

    return slots


def book_meeting(start: datetime, end: datetime, summary: str, *, description: str = "") -> JsonObject:
    """Books a real event on the shared calendar. Returns the created event object."""
    service = _calendar_service()
    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }
    return service.events().insert(calendarId=_calendar_id(), body=event).execute()
