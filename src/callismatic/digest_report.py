"""Generates a short, human-readable summary of what the agent has done --
the counterweight to a system whose whole design is to act silently on your
behalf. Without this, "quiet by design" and "acting without oversight"
would look identical from the outside.

Delivery is deliberately left open here: today `send_digest` only supports
"stdout" and "file", since neither needs a new credential. A real deployment
would add a "whatsapp" or "sms" channel (via the WhatsApp Business Cloud API
or Twilio) or "email" (via SendGrid or plain SMTP) -- each is a small
addition once a delivery channel and its credential are chosen, not a
redesign of this module.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

DIGEST_PATH = Path("outputs/digest.json")
BLOCKLIST_PATH = Path("outputs/blocklist.json")


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _within_window(timestamp_iso: str, since: datetime) -> bool:
    try:
        timestamp = datetime.fromisoformat(timestamp_iso)
    except ValueError:
        return False
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp >= since


def generate_weekly_digest(*, days: int = 7, now: datetime | None = None) -> str:
    """Builds a plain-text summary of everything triaged in the last `days` days:
    how many voicemails/messages needed a decision, how many callbacks were placed,
    how many numbers were blocked, and how many were filed silently."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    digest_entries = [e for e in _load(DIGEST_PATH) if _within_window(e["triaged_at"], since)]
    blocklist_entries = [e for e in _load(BLOCKLIST_PATH) if _within_window(e["blocked_at"], since)]

    needs_decision = [e for e in digest_entries if e["triage"].get("needs_decision")]
    callbacks_recommended = [e for e in digest_entries if e["triage"].get("callback_recommended")]
    filed_silently = [
        e
        for e in digest_entries
        if not e["triage"].get("needs_decision")
        and not e["triage"].get("callback_recommended")
        and not e["triage"].get("block_recommended")
    ]

    lines = [
        f"Callismatic weekly digest -- {since.date().isoformat()} to {now.date().isoformat()}",
        "",
        f"Triaged: {len(digest_entries)} voicemail(s)/message(s)",
        f"  - {len(needs_decision)} needed your decision",
        f"  - {len(callbacks_recommended)} recommended for callback",
        f"  - {len(blocklist_entries)} number(s) blocked",
        f"  - {len(filed_silently)} filed silently, no action needed",
    ]

    if needs_decision:
        lines.append("")
        lines.append("Still needing your attention:")
        for entry in needs_decision[-5:]:
            lines.append(f"  - {entry['file']}: {entry['triage'].get('summary', '')}")

    if blocklist_entries:
        lines.append("")
        lines.append("Blocked this period:")
        for entry in blocklist_entries[-5:]:
            lines.append(f"  - {entry['phone_number']}: {entry.get('reason', '')}")

    return "\n".join(lines)


def send_digest(text: str, channel: Literal["stdout", "file"] = "stdout", *, path: Path | None = None) -> None:
    """Delivers the digest. "stdout" prints it; "file" writes/appends it to `path`
    (default: outputs/digest_report_<today>.txt). Neither needs a delivery credential --
    a real WhatsApp/SMS/email channel is the natural next addition once one is chosen."""
    if channel == "stdout":
        print(text)
        return
    if channel == "file":
        target = path or Path(f"outputs/digest_report_{date.today().isoformat()}.txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return
    raise ValueError(f"Unsupported digest delivery channel: {channel}")
