"""A to-do list, mostly for free: every triage decision with needs_decision=true and a
suggested_action already IS a to-do item -- this module just makes that explicit,
persisted, and completable, instead of leaving it to live only inside the terminal
report from whichever run produced it.

Items can also be added directly (not derived from a triage decision) via `add_todo`,
for anything that doesn't originate from a call.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TODOS_PATH = Path("outputs/todos.json")

JsonObject = dict[str, Any]

# Guards the read-modify-write below -- triage_inbox_concurrent (triage.py) can call
# add_todo_from_triage from multiple worker threads at once; see the identical comment
# on tools._digest_lock for why this is a real, not hypothetical, hazard.
_todos_lock = threading.Lock()


def _sync_to_todoist_if_configured(text: str) -> None:
    """Best-effort Todoist sync, same pattern as triage._sync_to_crm_if_configured: only
    runs if TODOIST_API_TOKEN is set, and a failure here is logged, never raised -- a
    Todoist outage must not stop a to-do item from being recorded locally."""
    if not os.environ.get("TODOIST_API_TOKEN"):
        return
    try:
        from callismatic.todoist_sync import create_todoist_task

        create_todoist_task(text)
    except Exception as e:  # noqa: BLE001 -- deliberate: Todoist sync is a side channel, never a blocker
        print(f"Warning: Todoist sync failed: {e}", file=sys.stderr)


def _load() -> list[JsonObject]:
    if not TODOS_PATH.exists():
        return []
    return json.loads(TODOS_PATH.read_text(encoding="utf-8"))


def _save(items: list[JsonObject]) -> None:
    TODOS_PATH.parent.mkdir(parents=True, exist_ok=True)
    TODOS_PATH.write_text(json.dumps(items, indent=2), encoding="utf-8")


def add_todo(text: str, *, source: str = "manual", due: str | None = None) -> JsonObject:
    """Adds a new to-do item and returns it. `source` is the triage file_name/message_id
    this came from, or "manual" for one added directly."""
    with _todos_lock:
        items = _load()
        item = {
            "id": f"todo-{len(items) + 1}",
            "text": text,
            "source": source,
            "due": due,
            "done": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
        }
        items.append(item)
        _save(items)
    _sync_to_todoist_if_configured(text)  # a network call -- kept outside the lock deliberately
    return item


def add_todo_from_triage(source_name: str, suggested_action: str) -> JsonObject:
    """Adds a to-do item derived from a triage decision's suggested_action."""
    return add_todo(suggested_action, source=source_name)


def list_todos(*, include_done: bool = False) -> list[JsonObject]:
    items = _load()
    if include_done:
        return items
    return [item for item in items if not item["done"]]


def complete_todo(item_id: str) -> bool:
    """Marks a to-do item done. Returns True if a matching item was found."""
    with _todos_lock:
        items = _load()
        found = False
        for item in items:
            if item["id"] == item_id and not item["done"]:
                item["done"] = True
                item["completed_at"] = datetime.now(timezone.utc).isoformat()
                found = True
        if found:
            _save(items)
    return found
