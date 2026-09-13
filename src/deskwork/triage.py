"""Scans a folder of voicemail recordings and triages every one of them, one
agent call each. Deterministic side effects -- an actual callback via
CALL-E, or adding a number to the blocklist -- happen here, after the agent
has already returned its structured decision, never inside the agent's own
tool-call loop."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from strands import Agent

from deskwork.callback import place_callback
from deskwork.schema import CallTriage
from deskwork.tools import block_number, record_decision
from deskwork.voicemails import transcribe_voicemail

SUPPORTED_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac"}
_PHONE_RE = re.compile(r"(\+\d{8,15})")


@dataclass
class TriageResult:
    file_name: str
    caller_number: str
    triage: CallTriage
    callback_result: dict | None = None
    error: str | None = None


def caller_number_from_filename(path: Path) -> str:
    """Pulls a caller phone number out of the sample voicemail's filename.

    A real deployment would get this from telephony metadata (Twilio's
    caller-ID webhook field, for example); the demo samples encode it in the
    filename instead so the pipeline doesn't need a live phone line to
    exercise caller-number-driven behavior (blocking, callback) end to end.
    """
    match = _PHONE_RE.search(path.stem)
    return match.group(1) if match else "unknown"


def triage_inbox(agent: Agent, inbox_dir: Path, *, place_callbacks: bool = True) -> list[TriageResult]:
    results = []
    for path in sorted(inbox_dir.iterdir()):
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        results.append(_triage_one(agent, path, place_callbacks=place_callbacks))
    return results


def _triage_one(agent: Agent, path: Path, *, place_callbacks: bool) -> TriageResult:
    caller_number = caller_number_from_filename(path)
    try:
        transcript = transcribe_voicemail(path)
    except RuntimeError as e:
        return TriageResult(file_name=path.name, caller_number=caller_number, triage=None, error=str(e))  # type: ignore[arg-type]

    prompt = (
        f"Triage this voicemail.\n\nFile name: {path.name}\nCaller number: {caller_number}\n\n"
        f"Transcript:\n{transcript}"
    )
    response = agent(prompt, structured_output_model=CallTriage)
    triage: CallTriage = response.structured_output

    record_decision(path.name, triage.model_dump())

    if triage.block_recommended:
        block_number(caller_number, triage.decision_reason or triage.summary)

    callback_result = None
    if triage.callback_recommended and triage.callback_task and place_callbacks and caller_number != "unknown":
        callback_result = place_callback(triage.callback_task, caller_number)

    return TriageResult(
        file_name=path.name,
        caller_number=caller_number,
        triage=triage,
        callback_result=callback_result,
    )
