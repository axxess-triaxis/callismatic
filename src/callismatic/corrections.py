"""Persists human corrections to past triage decisions.

This is the mechanism that closes the loop between "the agent got this
wrong" and "the agent doesn't repeat it": a human runs `callismatic correct
...` (see cli.py), which records what the agent decided vs. what it should
have decided, and the agent checks this log (via the check_corrections tool
in tools.py) before making a new decision about a caller it may have
misjudged before.

Corrections are only ever written by the CLI, never by the agent itself --
the same confirm-before-critical-action boundary as block_number and
place_callback, just running in the other direction: a human overriding the
agent, not the agent acting on its own.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

from callismatic.paths import DATA_DIR

CORRECTIONS_PATH = DATA_DIR / "corrections.json"

# Not currently called from any concurrent path (only the single-threaded CLI `correct`
# command), but guarded for the same reason as tools._digest_lock/todos._todos_lock: cheap
# insurance against a future concurrent caller reintroducing the same read-modify-write race.
_corrections_lock = threading.Lock()


def record_correction(target: str, original: dict[str, Any], corrected: dict[str, Any], reason: str) -> None:
    """Appends one human correction to the persistent log.

    target is typically a phone number (for an unblock) or a voicemail file
    name (for a recategorization) -- whatever check_corrections should later
    search for.
    """
    with _corrections_lock:
        CORRECTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        entries = json.loads(CORRECTIONS_PATH.read_text(encoding="utf-8")) if CORRECTIONS_PATH.exists() else []
        entries.append(
            {
                "target": target,
                "original": original,
                "corrected": corrected,
                "reason": reason,
                "corrected_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        CORRECTIONS_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def find_corrections(keyword: str) -> list[dict[str, Any]]:
    """Returns past corrections whose target, reason, or correction mentions keyword."""
    if not CORRECTIONS_PATH.exists():
        return []
    entries = json.loads(CORRECTIONS_PATH.read_text(encoding="utf-8"))
    keyword_lower = keyword.lower()
    return [e for e in entries if keyword_lower in json.dumps(e).lower()]
