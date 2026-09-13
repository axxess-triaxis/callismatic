"""A local reminder store: persist a message to be sent at/after a due time, then
check for and send due reminders when invoked -- meant to be run periodically (a
cron job, a scheduled task), the same way `callismatic digest` is meant to be run
periodically rather than kept running continuously.

Delivery defaults to WhatsApp (send_whatsapp_message in whatsapp_webhook.py), since
that's the channel already fully wired and verified live this session. Falls back to
stdout if WhatsApp isn't configured or delivery fails, so a reminder is never silently
lost even before WHATSAPP_ACCESS_TOKEN/WHATSAPP_PHONE_NUMBER_ID exist.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from callismatic.paths import DATA_DIR

REMINDERS_PATH = DATA_DIR / "reminders.json"

JsonObject = dict[str, Any]


def _load() -> list[JsonObject]:
    if not REMINDERS_PATH.exists():
        return []
    return json.loads(REMINDERS_PATH.read_text(encoding="utf-8"))


def _save(items: list[JsonObject]) -> None:
    REMINDERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    REMINDERS_PATH.write_text(json.dumps(items, indent=2), encoding="utf-8")


def _as_aware_utc(timestamp: datetime) -> datetime:
    return timestamp if timestamp.tzinfo is not None else timestamp.replace(tzinfo=timezone.utc)


def add_reminder(text: str, due_at: str, *, to: str | None = None) -> JsonObject:
    """Schedules a reminder. `due_at` is an ISO 8601 timestamp; `to` is the WhatsApp number
    to deliver it to (omit to have it only ever print via stdout when due)."""
    items = _load()
    item = {
        "id": f"reminder-{len(items) + 1}",
        "text": text,
        "due_at": due_at,
        "to": to,
        "sent": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    items.append(item)
    _save(items)
    return item


def due_reminders(*, now: datetime | None = None) -> list[JsonObject]:
    """Returns unsent reminders whose due_at has already passed."""
    now = _as_aware_utc(now or datetime.now(timezone.utc))
    return [
        item
        for item in _load()
        if not item["sent"] and _as_aware_utc(datetime.fromisoformat(item["due_at"])) <= now
    ]


def send_due_reminders(*, now: datetime | None = None) -> list[JsonObject]:
    """Delivers every due, unsent reminder and marks each sent. Returns the list actually sent."""
    items = _load()
    now = _as_aware_utc(now or datetime.now(timezone.utc))
    sent: list[JsonObject] = []
    for item in items:
        if item["sent"] or _as_aware_utc(datetime.fromisoformat(item["due_at"])) > now:
            continue
        _deliver(item)
        item["sent"] = True
        sent.append(item)
    if sent:
        _save(items)
    return sent


def _deliver(item: JsonObject) -> None:
    if item.get("to"):
        try:
            from callismatic.whatsapp_webhook import send_whatsapp_message

            send_whatsapp_message(item["to"], f"Reminder: {item['text']}")
            return
        except Exception as e:  # noqa: BLE001 -- fall back to stdout rather than losing the reminder
            print(f"Warning: WhatsApp reminder delivery failed, printing instead: {e}")
    print(f"Reminder: {item['text']}")
