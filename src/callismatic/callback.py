"""Places a real outbound call via the CALL-E platform.

Not exposed as an @tool to the triage agent -- placing a phone call is a
real-world side effect with cost and consequence, so it happens exactly
once, deterministically, driven by the agent's own already-finished
callback_recommended/callback_task decision -- the same pattern as
tools.record_decision and tools.block_number. The agent never gets to
freely re-trigger a call mid-reasoning.
"""

from __future__ import annotations

import os
from typing import Any

from calle import CalleClient

JsonObject = dict[str, Any]


def place_callback(task: str, phone_number: str) -> JsonObject:
    """Places a real CALL-E call and waits for it to finish, returning CALL-E's result object
    (status, transcript, any structured data extracted during the call).

    Raises RuntimeError if CALLE_API_KEY is not set.
    """
    api_key = os.environ.get("CALLE_API_KEY")
    if not api_key:
        raise RuntimeError("CALLE_API_KEY is not set -- see .env.example.")
    client = CalleClient(api_key=api_key)
    try:
        return client.calls.create_and_wait(task=task, recipient={"phone": phone_number})
    finally:
        client.close()
