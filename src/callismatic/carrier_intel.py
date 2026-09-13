"""Supplements the transcript-content scam heuristic (tools.check_number_intel)
with a second, independent signal: the destination number's real carrier/line
type, via Twilio Lookup.

This does not replace the transcript heuristic -- VOIP-originated numbers are
disproportionately used for scam/robocall traffic, but plenty of legitimate
callers (a small business on a VOIP PBX) use VOIP too, so this is evidence
for the agent to weigh, not a verdict, exactly like check_number_intel.

Needs TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN (from https://console.twilio.com).
Twilio Lookup's Line Type Intelligence add-on has a small per-lookup cost --
unlike the transcript heuristic, this is not a free check.
"""

from __future__ import annotations

import os


def check_carrier_intel(phone_number: str) -> str:
    """Looks up a phone number's line type and carrier via Twilio Lookup.

    Returns a short text report, or an explanation if credentials are
    missing or the lookup fails -- never raises, since a missing/failed
    carrier check should degrade to "no signal," not crash triage.
    """
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        return "Carrier intelligence unavailable: TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN not set."

    from twilio.base.exceptions import TwilioRestException
    from twilio.rest import Client

    client = Client(account_sid, auth_token)
    try:
        lookup = client.lookups.v2.phone_numbers(phone_number).fetch(fields="line_type_intelligence")
    except TwilioRestException as exc:
        return f"Carrier intelligence lookup failed: {exc}"

    line_type_intel = lookup.line_type_intelligence or {}

    error_code = line_type_intel.get("error_code")
    if error_code:
        return (
            f"Carrier intelligence unavailable (Twilio error {error_code}) -- e.g. 60627 means "
            "a trial account's Lookup quota has been reached; this is a Twilio account-level "
            "limit, not a signal about the caller."
        )

    line_type = line_type_intel.get("type", "unknown")
    carrier_name = line_type_intel.get("carrier_name", "unknown")
    return (
        f"Carrier intelligence: line type={line_type}, carrier={carrier_name}. "
        "(VOIP lines are disproportionately used for scam/robocall traffic, but "
        "legitimate businesses use VOIP too -- this is evidence, not a verdict.)"
    )
