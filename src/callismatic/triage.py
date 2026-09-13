"""Scans a folder of voicemail recordings (or a batch of SMS/WhatsApp
messages) and triages every one of them, one agent call each. Deterministic
side effects -- an actual callback via CALL-E, or adding a number to the
blocklist -- happen here, after the agent has already returned its
structured decision, never inside the agent's own tool-call loop.

Voicemail and text-message intake share everything downstream of "how the
transcript text was obtained": the same CallTriage schema, the same agent,
the same block/callback/record actions. A voicemail's transcript comes from
AssemblyAI; an SMS/WhatsApp message's "transcript" is just the message body
-- no transcription step needed. Actually receiving live SMS/WhatsApp
messages needs its own webhook server and provider credentials (Twilio SMS,
or Meta's WhatsApp Business Cloud API) -- outside what this module does;
what it does provide is triage_text_message, ready for whatever receives
those messages to call.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from strands import Agent

from callismatic.call_router import route_call
from callismatic.schema import CallTriage
from callismatic.tools import block_number, record_decision
from callismatic.voicemails import transcribe_voicemail

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


def triage_text_message(
    agent: Agent,
    channel: Literal["sms", "whatsapp"],
    sender: str,
    message_id: str,
    body: str,
    *,
    place_callbacks: bool = True,
) -> TriageResult:
    """Triages one already-received SMS/WhatsApp message through the same pipeline as a
    voicemail -- no transcription step, since the message body already is the text to reason
    over. `message_id` plays the same role `file_name` plays for a voicemail: a stable label
    for this event in the digest/blocklist/corrections logs."""
    return _decide_and_act(
        agent,
        source_name=f"{channel}:{message_id}",
        caller_number=sender,
        transcript=body,
        intake_label=f"{channel.upper()} message",
        place_callbacks=place_callbacks,
    )


def _triage_one(agent: Agent, path: Path, *, place_callbacks: bool) -> TriageResult:
    caller_number = caller_number_from_filename(path)
    try:
        transcript = transcribe_voicemail(path)
    except RuntimeError as e:
        return TriageResult(file_name=path.name, caller_number=caller_number, triage=None, error=str(e))  # type: ignore[arg-type]

    return _decide_and_act(
        agent,
        source_name=path.name,
        caller_number=caller_number,
        transcript=transcript,
        intake_label="voicemail",
        place_callbacks=place_callbacks,
    )


def _decide_and_act(
    agent: Agent,
    *,
    source_name: str,
    caller_number: str,
    transcript: str,
    intake_label: str,
    place_callbacks: bool,
) -> TriageResult:
    prompt = (
        f"Triage this {intake_label}.\n\nSource: {source_name}\nCaller number: {caller_number}\n\n"
        f"Transcript:\n{transcript}"
    )
    response = agent(prompt, structured_output_model=CallTriage)
    triage: CallTriage = response.structured_output

    record_decision(source_name, triage.model_dump())
    _sync_to_crm_if_configured(source_name, caller_number, triage)

    if triage.block_recommended:
        block_number(caller_number, triage.decision_reason or triage.summary)

    callback_result = None
    if triage.callback_recommended and triage.callback_task and place_callbacks and caller_number != "unknown":
        callback_result = route_call(triage.callback_task, caller_number)

    return TriageResult(
        file_name=source_name,
        caller_number=caller_number,
        triage=triage,
        callback_result=callback_result,
    )


def _sync_to_crm_if_configured(source_name: str, caller_number: str, triage: CallTriage) -> None:
    """Best-effort CRM sync: only runs if GOOGLE_SHEET_ID is set, and a failure here is
    logged, never raised -- a CRM outage or misconfiguration must not stop triage from
    recording its decision and taking the block/callback action it already decided on."""
    if not os.environ.get("GOOGLE_SHEET_ID"):
        return
    try:
        from callismatic.crm_sheets import sync_lead_to_sheet

        sync_lead_to_sheet(datetime.now(timezone.utc).isoformat(), source_name, caller_number, triage)
    except Exception as e:  # noqa: BLE001 -- deliberate: CRM sync is a side channel, never a blocker
        print(f"Warning: CRM sync to Google Sheets failed: {e}", file=sys.stderr)
