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
import threading
from datetime import date, datetime, timezone
from pathlib import Path

from strands import tool

from callismatic.carrier_intel import check_carrier_intel as _check_carrier_intel
from callismatic.corrections import find_corrections

DIGEST_PATH = Path("outputs/digest.json")
BLOCKLIST_PATH = Path("outputs/blocklist.json")

# Guards the read-modify-write on each file below. Needed because
# triage_inbox_concurrent (triage.py) runs multiple sub-agents' record_decision/
# block_number calls on separate worker threads via asyncio.to_thread -- without
# this, two sub-agents finishing at the same instant can both read the same
# pre-append file contents, then each write back a version missing the other's
# entry (or, if the writes themselves interleave, corrupt the file into invalid
# JSON entirely). A real occurrence of exactly that, not a hypothetical: this was
# found by test_triage_inbox_concurrent_spawns_one_fresh_agent_per_voicemail
# intermittently failing with JSONDecodeError before this lock was added.
_digest_lock = threading.Lock()
_blocklist_lock = threading.Lock()

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


@tool
def check_corrections(keyword: str) -> str:
    """Searches human corrections to past triage decisions for a keyword (typically the
    caller's phone number, or a voicemail file name) so a mistake this agent made before
    -- wrongly blocking a real caller, wrongly staying silent on something that mattered --
    isn't repeated for the same caller or pattern.

    Args:
        keyword: a term to search for -- typically the caller's phone number.

    Returns a short text report of matching corrections, or a message saying none were found.
    Treat any match as ground truth from a human, overriding your own judgment for this caller.
    """
    matches = find_corrections(keyword)
    if not matches:
        return f"No human corrections mention '{keyword}'."
    lines = [
        f"- {m['target']} ({m['corrected_at']}): corrected to {m['corrected']} -- reason: {m['reason']}"
        for m in matches[-5:]
    ]
    return "Matching corrections (treat as ground truth, overriding your own judgment):\n" + "\n".join(lines)


@tool
def check_carrier_intel(phone_number: str) -> str:
    """Looks up a caller's real line type and carrier (mobile/landline/VOIP) via Twilio
    Lookup -- a second, independent signal alongside check_number_intel's transcript-content
    scan. VOIP lines are disproportionately used for scam/robocall traffic, but legitimate
    small businesses use VOIP too, so this is evidence to weigh, never a verdict on its own.

    Args:
        phone_number: the caller's phone number in E.164 format.

    Returns a short text report, or a note that carrier intelligence is unavailable if
    TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN aren't configured -- absence of this signal should
    never block a decision the transcript heuristic can make on its own.
    """
    return _check_carrier_intel(phone_number)


def find_digest_entry(file_name: str) -> dict | None:
    """Returns the most recent digest entry recorded for a given voicemail file name, or None."""
    if not DIGEST_PATH.exists():
        return None
    entries = json.loads(DIGEST_PATH.read_text(encoding="utf-8"))
    matches = [e for e in entries if e["file"] == file_name]
    return matches[-1] if matches else None


def unblock_number(phone_number: str) -> bool:
    """Removes every blocklist entry for a phone number. Returns True if anything was removed.

    Not exposed as an @tool -- unblocking is a human correction action
    (see corrections.py / `callismatic correct unblock`), never something
    the agent decides to undo on its own.
    """
    with _blocklist_lock:
        if not BLOCKLIST_PATH.exists():
            return False
        entries = json.loads(BLOCKLIST_PATH.read_text(encoding="utf-8"))
        remaining = [e for e in entries if e["phone_number"] != phone_number]
        removed = len(remaining) != len(entries)
        BLOCKLIST_PATH.write_text(json.dumps(remaining, indent=2), encoding="utf-8")
    return removed


def record_decision(file_name: str, triage: dict) -> None:
    """Appends one triaged voicemail's record to the persistent digest log.

    Not exposed as an @tool -- the CLI calls this directly after the agent
    returns its structured output, so the log always reflects exactly what
    was decided, never something the model could omit or alter mid-reasoning.
    """
    with _digest_lock:
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
    with _blocklist_lock:
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
