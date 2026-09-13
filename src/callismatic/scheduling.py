"""Turns raw calendar availability (calendar_sync.find_free_slots) into a natural-language
offer suitable for a CALL-E callback_task, and books whichever slot the caller picks.

calendar_sync only reads/writes events -- this is the layer that makes availability usable
inside an actual phone conversation. CALL-E's own agent conducts the call using the text
propose_slots_text produces (embedded in the task it's given) and returns which slot, if any,
the caller picked in its structured_result; book_chosen_slot turns that pick into a real event.
"""

from __future__ import annotations

from datetime import datetime

from callismatic.calendar_sync import book_meeting, find_free_slots


def _format_slot(start: datetime) -> str:
    # %-I (no leading zero) is a glibc/Unix strftime extension, not portable to Windows --
    # format with the zero-padded %I and strip it manually instead.
    time_str = start.strftime("%I:%M %p").lstrip("0")
    return start.strftime("%A %b %d") + " at " + time_str


def propose_slots_text(duration_minutes: int = 30, *, days_ahead: int = 7, max_slots: int = 3) -> str:
    """Returns a short, natural-language list of the next available slots -- e.g.
    "Tuesday Sep 15 at 2:00 PM, Wednesday Sep 16 at 10:00 AM" -- ready to drop into a CALL-E
    callback_task like: f"Offer these times: {propose_slots_text()}"."""
    slots = find_free_slots(duration_minutes, days_ahead=days_ahead)[:max_slots]
    if not slots:
        return "no availability found in the next week"
    return ", ".join(_format_slot(start) for start, _ in slots)


def book_chosen_slot(start: datetime, end: datetime, summary: str, attendee_description: str) -> dict:
    """Books the slot the caller actually picked (from CALL-E's structured_result), with a
    description crediting who it's for."""
    return book_meeting(start, end, summary, description=attendee_description)
