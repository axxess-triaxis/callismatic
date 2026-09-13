"""Tools the triage agent can call mid-reasoning.

Both exist because a single-shot "read text, classify it" call can't do two
things a real assistant needs: know what day it is (to tell "due in 3 weeks"
from "overdue"), and remember what it already told you (to avoid re-flagging
the same invoice every run). Giving the agent tools for these, rather than
computing them in Python and stuffing the answer into the prompt, is what
makes this an agent decision rather than a template fill.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from strands import tool

DIGEST_PATH = Path("outputs/digest.json")


@tool
def get_today() -> str:
    """Returns today's date as an ISO string (YYYY-MM-DD), for judging deadlines and overdue items."""
    return date.today().isoformat()


@tool
def check_past_decisions(keyword: str) -> str:
    """Searches previously triaged documents for a keyword (e.g. a vendor name, invoice number,
    or counterparty) to check whether something related was already reviewed and decided on.

    Args:
        keyword: a term to search for in past summaries and key facts.

    Returns a short text report of matching past entries, or a message saying none were found.
    """
    if not DIGEST_PATH.exists():
        return "No past decisions recorded yet -- this is the first run."

    entries = json.loads(DIGEST_PATH.read_text(encoding="utf-8"))
    keyword_lower = keyword.lower()
    matches = [
        e
        for e in entries
        if keyword_lower in json.dumps(e).lower()
    ]
    if not matches:
        return f"No past entries mention '{keyword}'."

    lines = [
        f"- {m['file']} ({m['triaged_at']}): {m['triage']['summary']}"
        for m in matches[-5:]
    ]
    return "Matching past entries:\n" + "\n".join(lines)


def record_decision(file_name: str, triage: dict) -> None:
    """Appends one triaged document's record to the persistent digest log.

    Not exposed as an @tool -- the CLI calls this directly after the agent
    returns its structured output, so the log always reflects exactly what
    was decided, never something the model could omit or alter mid-reasoning.
    """
    DIGEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    entries = json.loads(DIGEST_PATH.read_text(encoding="utf-8")) if DIGEST_PATH.exists() else []
    entries.append(
        {
            "file": file_name,
            "triaged_at": datetime.now(timezone.utc).isoformat(),
            "triage": triage,
        }
    )
    DIGEST_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")
