"""Tools the triage agent can call mid-reasoning, plus the deterministic
persistence functions that run *after* the agent has already decided.

get_today and check_number_intel exist because a single-shot "read
transcript, classify it" call can't do things a real assistant needs: know
what day it is, and check a transcript against concrete scam-script markers
rather than vibes. check_past_decisions exists so a caller already handled
in a prior run isn't re-flagged every time.

record_decision and block_number are deliberately NOT @tool functions --
writing the digest log and adding a number to the blocklist are real side
effects that should happen exactly once, driven by the agent's own already-
finished decision, never something the model can trigger freely mid-
reasoning. This mirrors the confirm-before-critical-action pattern.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from strands import tool

DIGEST_PATH = Path("outputs/digest.json")
BLOCKLIST_PATH = Path("outputs/blocklist.json")

_SCAM_MARKERS: dict[str, list[str]] = {
    "gift-card payment request": ["gift card", "itunes card", "google play card", "steam card"],
    "wire/crypto payment request": ["wire transfer", "bitcoin", "crypto wallet", "cash app"],
    "threat/urgency pressure": [
        "arrest warrant",
        "suspended",
        "act immediately",
        "final notice",
        "legal action",
        "within 24 hours",
        "within twenty four hours",
    ],
    "government/agency impersonation": [
        "irs",
        "social security administration",
        "federal fraud",
        "medicare fraud department",
    ],
}


@tool
def get_today() -> str:
    """Returns today's date as an ISO string (YYYY-MM-DD), for judging deadlines and how stale a callback request has become."""
    return date.today().isoformat()


@tool
def check_past_decisions(keyword: str) -> str:
    """Searches previously triaged voicemails for a keyword (e.g. a phone number, caller name,
    or company) to check whether this caller was already reviewed and decided on.

    Args:
        keyword: a term to search for in past summaries and key facts.

    Returns a short text report of matching past entries, or a message saying none were found.
    """
    if not DIGEST_PATH.exists():
        return "No past decisions recorded yet -- this is the first run."

    entries = json.loads(DIGEST_PATH.read_text(encoding="utf-8"))
    keyword_lower = keyword.lower()
    matches = [e for e in entries if keyword_lower in json.dumps(e).lower()]
    if not matches:
        return f"No past entries mention '{keyword}'."

    lines = [
        f"- {m['file']} ({m['triaged_at']}): {m['triage']['summary']}"
        for m in matches[-5:]
    ]
    return "Matching past entries:\n" + "\n".join(lines)


@tool
def check_number_intel(transcript_excerpt: str) -> str:
    """Runs a lightweight, honest scam/spam signal check over a voicemail transcript.

    This project does not integrate with Truecaller or any other proprietary
    carrier/reputation database -- there is no public developer API for
    that. Instead this scans the transcript itself for concrete scam-script
    markers: gift-card/wire/crypto payment requests, urgency or legal-threat
    pressure, and government-agency impersonation. This is one heuristic
    signal for the agent to weigh, not an automatic verdict.

    Args:
        transcript_excerpt: the voicemail transcript (or the relevant part of it) to scan.

    Returns a short text report of which scam markers were found, if any.
    """
    text_lower = transcript_excerpt.lower()
    found = [
        label
        for label, phrases in _SCAM_MARKERS.items()
        if any(phrase in text_lower for phrase in phrases)
    ]
    if not found:
        return "No scam-script markers found in the transcript."
    return (
        "Scam-script markers found: "
        + ", ".join(found)
        + ". (Heuristic signal from transcript content only -- no Truecaller or carrier-"
        "database lookup is used, since no public API for that exists.)"
    )


def record_decision(file_name: str, triage: dict) -> None:
    """Appends one triaged voicemail's record to the persistent digest log.

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


def block_number(phone_number: str, reason: str) -> None:
    """Appends a phone number to the persistent blocklist.

    Not exposed as an @tool for the same reason record_decision isn't:
    blocking a real number is a side effect that should happen exactly
    once, deterministically, after the agent has already decided
    block_recommended=true.
    """
    BLOCKLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    entries = json.loads(BLOCKLIST_PATH.read_text(encoding="utf-8")) if BLOCKLIST_PATH.exists() else []
    entries.append(
        {
            "phone_number": phone_number,
            "reason": reason,
            "blocked_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    BLOCKLIST_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")
