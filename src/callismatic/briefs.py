"""Pre-meeting briefs: for each meeting coming up on the calendar, work out which
organisation it's with, look that organisation up on the web (SerpApi Google Search for
who they are, Google News for what's happening with them right now), and deliver a short
brief before the meeting -- via the same reminder channel (WhatsApp, or stdout) that
reminders.py already uses.

This is the secretary half of Callismatic doing what a good human assistant does before
you walk into a call: "Your 3pm is with Zomato -- here's who they are and what's been in
the news this week."

Built for the SerpApi India Hackathon 2026. Needs SERPAPI_API_KEY; the calendar side
needs GOOGLE_SERVICE_ACCOUNT_FILE + GOOGLE_CALENDAR_ID (see calendar_sync.py), but
`brief_for_company` works without a calendar at all.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from callismatic.web_intel import company_news, company_overview

JsonObject = dict[str, Any]

DEFAULT_LEAD_MINUTES = 30

# Attendees on these domains are individuals, not an organisation worth researching.
PERSONAL_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "outlook.com", "hotmail.com",
    "live.com", "icloud.com", "me.com", "proton.me", "protonmail.com", "rediffmail.com", "aol.com",
}
_WITH_RE = re.compile(r"\bwith\s+([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3})")


def _own_domain() -> str:
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", "")
    return calendar_id.split("@", 1)[1].lower() if "@" in calendar_id else ""


def organisation_for_event(event: JsonObject) -> str | None:
    """Best guess at the organisation a meeting is with.

    1. The first attendee email domain that isn't a personal-mail provider or your own
       domain ("priya@zomato.com" -> "zomato").
    2. Otherwise "... with <Capitalised Name>" in the event title ("Call with Acme Logistics").
    Returns None when there's nothing to research (e.g. an internal or personal event).
    """
    own = _own_domain()
    for email in event.get("attendee_emails", []):
        domain = email.rsplit("@", 1)[-1].lower()
        if domain in PERSONAL_EMAIL_DOMAINS or domain == own:
            continue
        labels = domain.split(".")
        # zomato.com -> zomato; tcs.co.in -> tcs; mail.acme.io -> acme
        core = labels[-3] if len(labels) >= 3 and labels[-2] in {"co", "com", "org", "net", "gov", "ac"} else labels[-2] if len(labels) >= 2 else labels[0]
        return core
    match = _WITH_RE.search(event.get("summary", ""))
    return match.group(1).strip() if match else None


def brief_for_company(company: str, *, event: JsonObject | None = None, now: datetime | None = None) -> str:
    """Composes a short brief: who the organisation is, plus recent news. Web text is
    untrusted, so the brief says where it came from and to check before quoting it."""
    overview = company_overview(company, now=now)
    news = company_news(company, n=3, now=now)

    header = f"Brief: {company}"
    if event:
        header = f"Brief for \"{event.get('summary', 'meeting')}\" ({event.get('start', '')}) -- {company}"
    lines = [header]
    if overview:
        about = overview["name"]
        if overview.get("description"):
            about += f" -- {overview['description']}"
        if overview.get("website"):
            about += f" ({overview['website']})"
        lines.append(f"About: {about}")
    else:
        lines.append("About: no web profile found (or web intelligence unavailable).")
    if news:
        lines.append("Recent news:")
        lines += [f"- {n['title']} ({n['source']}{', ' + n['date'] if n['date'] else ''})" for n in news]
    else:
        lines.append("Recent news: none found.")
    lines.append("Source: web search via SerpApi (third-party text -- verify before quoting).")
    return "\n".join(lines)


def schedule_briefs(
    *,
    hours_ahead: int = 24,
    to: str | None = None,
    lead_minutes: int = DEFAULT_LEAD_MINUTES,
    dry_run: bool = False,
    now: datetime | None = None,
) -> list[JsonObject]:
    """Builds a brief for every upcoming meeting with an identifiable organisation and,
    unless dry_run, schedules it as a reminder `lead_minutes` before the meeting starts.
    Returns [{event, company, brief, due_at}] for each brief built."""
    from callismatic.calendar_sync import list_upcoming_events
    from callismatic.reminders import add_reminder

    now = now or datetime.now(timezone.utc)
    out: list[JsonObject] = []
    for event in list_upcoming_events(hours_ahead=hours_ahead, now=now):
        company = organisation_for_event(event)
        if not company or not event.get("start"):
            continue
        brief = brief_for_company(company, event=event, now=now)
        start = datetime.fromisoformat(event["start"])
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        due_at = max(start - timedelta(minutes=lead_minutes), now).isoformat()
        if not dry_run:
            add_reminder(brief, due_at, to=to)
        out.append({"event": event, "company": company, "brief": brief, "due_at": due_at})
    return out
