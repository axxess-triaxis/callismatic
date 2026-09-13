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

import asyncio
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from strands import Agent

from callismatic.agent import build_agent
from callismatic.call_router import route_call
from callismatic.schema import CallTriage
from callismatic.tools import block_number, record_decision
from callismatic.voicemails import transcribe_voicemail

DEFAULT_MAX_CONCURRENCY = 5

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


async def triage_inbox_concurrent(
    inbox_dir: Path,
    *,
    place_callbacks: bool = True,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
) -> list[TriageResult]:
    """Triages every voicemail in inbox_dir concurrently -- one freshly spawned sub-agent per
    voicemail, run via Strands' async invocation, instead of triage_inbox's sequential
    one-agent-call-at-a-time loop.

    Strands agents don't support safely reusing one instance across concurrent calls --
    ConcurrentInvocationMode.THROW (the default) raises ConcurrencyException if you try. So
    "spawn a sub-agent" here is literal, not a figure of speech: each concurrent task gets its
    own build_agent() instance, not a shared one.

    Concurrency is bounded by `max_concurrency` (a semaphore) so a large inbox doesn't fire
    unbounded simultaneous Bedrock/AssemblyAI/CALL-E requests and trip a rate limit. Blocking
    calls (transcription, the digest/blocklist writes, the CRM sync, the CALL-E call itself --
    which can take up to 10 minutes per call.wait_for_result's own default timeout) are pushed
    onto worker threads via asyncio.to_thread so one slow callback never stalls the other
    sub-agents' progress.
    """
    paths = [p for p in sorted(inbox_dir.iterdir()) if p.suffix.lower() in SUPPORTED_SUFFIXES]
    semaphore = asyncio.Semaphore(max_concurrency)
    tasks = [_triage_one_async(path, place_callbacks=place_callbacks, semaphore=semaphore) for path in paths]
    return await asyncio.gather(*tasks)


async def _triage_one_async(path: Path, *, place_callbacks: bool, semaphore: asyncio.Semaphore) -> TriageResult:
    caller_number = caller_number_from_filename(path)
    async with semaphore:
        try:
            transcript = await asyncio.to_thread(transcribe_voicemail, path)
        except RuntimeError as e:
            return TriageResult(file_name=path.name, caller_number=caller_number, triage=None, error=str(e))  # type: ignore[arg-type]

        agent = build_agent()  # this voicemail's own sub-agent -- never shared with another concurrent task
        return await _decide_and_act_async(
            agent,
            source_name=path.name,
            caller_number=caller_number,
            transcript=transcript,
            intake_label="voicemail",
            place_callbacks=place_callbacks,
        )


async def _decide_and_act_async(
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
    response = await agent.invoke_async(prompt, structured_output_model=CallTriage)
    triage: CallTriage = response.structured_output

    await asyncio.to_thread(record_decision, source_name, triage.model_dump())
    await asyncio.to_thread(_sync_to_crm_if_configured, source_name, caller_number, triage)

    if triage.block_recommended:
        await asyncio.to_thread(block_number, caller_number, triage.decision_reason or triage.summary)

    callback_result = None
    if triage.callback_recommended and triage.callback_task and place_callbacks and caller_number != "unknown":
        callback_result = await asyncio.to_thread(route_call, triage.callback_task, caller_number)

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
