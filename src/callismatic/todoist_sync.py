"""Syncs to-do items to Todoist via a personal API token -- unlike Google Tasks, Todoist's
REST API authenticates with a plain bearer token you generate yourself (Todoist Settings ->
Integrations -> Developer -> API token), no OAuth consent flow needed for your own account.

This is strictly opt-in, same pattern as crm_sheets.py: unset TODOIST_API_TOKEN and nothing
changes -- the local to-do list (todos.py) still works on its own.
"""

from __future__ import annotations

import os
from typing import Any

JsonObject = dict[str, Any]

API_BASE = "https://api.todoist.com/rest/v2"


def create_todoist_task(content: str, *, due_string: str | None = None, description: str = "") -> JsonObject:
    """Creates a real task in Todoist. Raises RuntimeError if TODOIST_API_TOKEN is not set,
    or propagates the API's own error on failure."""
    token = os.environ.get("TODOIST_API_TOKEN")
    if not token:
        raise RuntimeError("TODOIST_API_TOKEN is not set -- see README.md for setup.")

    import httpx

    payload: JsonObject = {"content": content, "description": description}
    if due_string:
        payload["due_string"] = due_string

    response = httpx.post(
        f"{API_BASE}/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()
