"""Outbound agent calls requested from AXXESS ("Call with agent", 2026-11-13).

AXXESS's contactability gate decides who may be called and sends one job here per click. This module
places the call through a provider registered for the destination country, turns the conversation
into an outcome AXXESS understands, and reports back on the STILL bus as `call.completed.v1`. STILL
then calls AXXESS's `log_agent_call` tool, and `create_meeting` (which waits for a human approval)
when the contact accepted a demo slot.

Deliberately separate from `call_router.route_call`, which falls back to CALL-E for every country:
CALL-E lists India as International tier, "intended primarily for development and call testing", and
a real India call placed through it was dialled and never rang. So a lead call only goes through a
provider registered in OUTBOUND_PROVIDERS_BY_COUNTRY_CODE. It is empty until a DLT-registered Indian
route (or a TDRA-registered UAE route) is contracted, so every job is refused as provider_unavailable.

Off unless OUTBOUND_AGENT_CALLS_ENABLED=true. The fake provider runs only on staging
(CALLISMATIC_STAGE=staging and OUTBOUND_FAKE_PROVIDER=true), never in production.

The event never carries the transcript or the phone number; the transcript stays here.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal
from zoneinfo import ZoneInfo

import phonenumbers
from pydantic import BaseModel, Field

from callismatic.still_emit import emit

JsonObject = dict[str, Any]
Provider = Callable[[str, str], JsonObject]

SOURCE = "triaxis.callismatic"
EVENT_TYPE = "call.completed.v1"
ENABLED_ENV = "OUTBOUND_AGENT_CALLS_ENABLED"
FAKE_ENV = "OUTBOUND_FAKE_PROVIDER"
JOB_EVENT_KEY = "callismatic_outbound_job"

CallOutcome = Literal["connected", "no_answer", "voicemail", "wrong_number", "call_back", "not_interested", "interested"]

TIME_ZONES = {"IN": "Asia/Kolkata", "AE": "Asia/Dubai"}
DEMO_MINUTES = 30

# Country calling code -> provider for calls to leads. Empty on purpose; see the module docstring.
OUTBOUND_PROVIDERS_BY_COUNTRY_CODE: dict[int, Provider] = {}

UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


class OutboundCallRequest(BaseModel):
    job_id: str = Field(pattern=UUID_PATTERN)
    lead_id: str = Field(pattern=UUID_PATTERN)
    organization_id: str = Field(pattern=UUID_PATTERN)
    phone_e164: str = Field(pattern=r"^\+[1-9]\d{6,14}$")
    country: Literal["IN", "AE"]
    title: str = Field(max_length=200)
    contact_name: str | None = Field(default=None, max_length=120)
    company: str | None = Field(default=None, max_length=200)


class ProviderUnavailable(RuntimeError):
    """No provider may place a lead call to this destination."""


class CallReport(BaseModel):
    """What the voice agent's call achieved, in AXXESS's terms."""

    outcome: CallOutcome = Field(description="The call result, using exactly one of the allowed values")
    summary: str = Field(description="One or two plain sentences on what happened. Never invent a detail.")
    action_items: list[str] = Field(default_factory=list, description="Concrete next steps the contact asked for or agreed to")
    accepted_slot_start: str | None = Field(
        default=None, description="ISO start time of the demo slot the contact accepted; must be one of the offered slots, else null"
    )
    follow_up_at: str | None = Field(default=None, description="ISO datetime the contact asked to be called back, else null")
    opted_out: bool = Field(default=False, description="True if the contact asked not to be called again")


def outbound_enabled() -> bool:
    return os.environ.get(ENABLED_ENV, "").strip().lower() == "true"


def _fake_allowed() -> bool:
    return os.environ.get(FAKE_ENV, "").strip().lower() == "true" and os.environ.get("CALLISMATIC_STAGE") == "staging"


def fake_provider(task: str, phone_number: str) -> JsonObject:
    """Staging only: a scripted conversation, so the pipeline can run end to end without a call."""
    return {
        "status": "COMPLETED",
        "fake": True,
        "transcript_turns": [
            {"speaker": "agent", "text": "Hello, this is an AI assistant calling for Triaxis Ventures. Is now a good time?"},
            {"speaker": "contact", "text": "Yes, go ahead. A demo sounds useful, the first time you offered works."},
        ],
    }


def provider_for(phone_number: str) -> Provider:
    """Returns the provider for a lead call, or raises ProviderUnavailable."""
    if _fake_allowed():
        return fake_provider
    try:
        country_code = phonenumbers.parse(phone_number).country_code
    except phonenumbers.NumberParseException as exc:
        raise ProviderUnavailable("unparseable number") from exc
    provider = OUTBOUND_PROVIDERS_BY_COUNTRY_CODE.get(country_code)
    if provider is None:
        raise ProviderUnavailable(f"no lead-call provider for +{country_code}")
    return provider


def offered_slots(country: str, *, now: datetime | None = None, find_slots: Callable[..., list] | None = None) -> list[tuple[datetime, datetime]]:
    """Up to three free demo slots from the founder's calendar, or none if the calendar is not set up."""
    if find_slots is None:
        try:
            from callismatic.calendar_sync import find_free_slots as find_slots
        except ImportError:
            return []
    try:
        return list(find_slots(DEMO_MINUTES, days_ahead=5, now=now))[:3]
    except Exception:  # noqa: BLE001 -- slots are optional; the agent asks for a time instead
        return []


def build_task(request: OutboundCallRequest, slots: list[tuple[datetime, datetime]]) -> str:
    """The instruction the voice agent receives. Founder-reviewed wording is required before enabling."""
    zone = ZoneInfo(TIME_ZONES[request.country])
    who = request.contact_name or "the person who answers"
    company = f" at {request.company}" if request.company else ""
    lines = [
        f"Call {who}{company}.",
        "First, say plainly that you are an AI assistant calling on behalf of Triaxis Ventures about AXXESS TRIaxis, "
        "and ask whether now is a good time. If not, ask when to call back and end the call politely.",
        "If they ask not to be called again, confirm that they will not be called again, and end the call.",
        f"Goal: find out whether they would like a {DEMO_MINUTES}-minute demo of AXXESS TRIaxis.",
        "Do not quote prices, make commitments, or describe features you were not told about. "
        "If they ask something you cannot answer, say the team will follow up by email.",
    ]
    if slots:
        times = "; ".join(start.astimezone(zone).strftime("%A %d %B at %I:%M %p") for start, _ in slots)
        lines.append(f"If they want a demo, offer these times ({TIME_ZONES[request.country]} time): {times}. Confirm exactly one.")
    else:
        lines.append("If they want a demo, ask which weekday and time suits them, and say the team will confirm by email.")
    return "\n".join(lines)


def classify_call(task: str, transcript_turns: list[JsonObject], slots: list[tuple[datetime, datetime]]) -> CallReport:
    """Turns the transcript into a CallReport with the triage model (Bedrock), like meeting_notes."""
    from strands import Agent

    from callismatic.meeting_notes import _format_transcript
    from callismatic.models import get_model

    offered = ", ".join(start.isoformat() for start, _ in slots) or "none"
    agent = Agent(
        model=get_model(),
        system_prompt=(
            "You record the result of a sales call an AI assistant just made. Use only what the transcript says. "
            "Never soften or invent an outcome."
        ),
    )
    prompt = f"The call's task was:\n{task}\n\nOffered demo slot starts (ISO): {offered}\n\nTranscript:\n{_format_transcript(transcript_turns)}"
    return agent(prompt, structured_output_model=CallReport).structured_output


def run_outbound_job(
    request: OutboundCallRequest,
    *,
    provider: Provider | None = None,
    classify: Callable[[str, list[JsonObject], list[tuple[datetime, datetime]]], CallReport] = classify_call,
    slots_fn: Callable[[str], list[tuple[datetime, datetime]]] = offered_slots,
    emit_fn: Callable[..., Any] = emit,
) -> JsonObject:
    """Places the call, reports it on STILL as call.completed.v1, and returns the event data."""
    data: JsonObject = {
        "job_id": request.job_id,
        "lead_id": request.lead_id,
        "organization_id": request.organization_id,
        "title": request.title,
        "status": "failed",
        "outcome": None,
        "summary": None,
        "action_items": [],
        "accepted_slot": None,
        "follow_up_at": None,
        "opted_out": False,
        "failure_reason": None,
    }
    try:
        place = provider or provider_for(request.phone_e164)
        slots = slots_fn(request.country)
        task = build_task(request, slots)
        result = place(task, request.phone_e164)
        turns = result.get("transcript_turns") or []
        report = classify(task, turns, slots) if turns else CallReport(outcome="no_answer", summary="")
        accepted = next(
            ({"starts_at": start.isoformat(), "ends_at": end.isoformat()} for start, end in slots
             if report.accepted_slot_start and _same_instant(report.accepted_slot_start, start)),
            None,
        )
        data.update(
            status="completed",
            outcome="not_interested" if report.opted_out else report.outcome,
            summary=report.summary[:1000],
            action_items=[item[:300] for item in report.action_items[:10]],
            accepted_slot=None if report.opted_out else accepted,
            follow_up_at=None if report.opted_out else _iso_or_none(report.follow_up_at),
            opted_out=report.opted_out,
        )
    except ProviderUnavailable:
        data["failure_reason"] = "provider_unavailable"
    except Exception:  # noqa: BLE001 -- the job must always report back, never vanish
        data["failure_reason"] = "call_error"
    emit_fn(SOURCE, EVENT_TYPE, data, key=request.job_id, subject=request.lead_id)
    return data


def _same_instant(iso: str, moment: datetime) -> bool:
    try:
        parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return abs(parsed - moment) < timedelta(minutes=1)


def _iso_or_none(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).isoformat()


def dispatch_outbound_job(request: OutboundCallRequest, *, lambda_client=None) -> None:
    """Runs the job after the HTTP response: an async self-invoke on Lambda (a call outlasts the
    request), or a background thread for a local run."""
    function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    if function_name:
        import json

        import boto3

        client = lambda_client or boto3.client("lambda")
        client.invoke(
            FunctionName=function_name,
            InvocationType="Event",
            Payload=json.dumps({JOB_EVENT_KEY: request.model_dump()}).encode("utf-8"),
        )
        return
    import threading

    threading.Thread(target=run_outbound_job, args=(request,), daemon=True).start()
