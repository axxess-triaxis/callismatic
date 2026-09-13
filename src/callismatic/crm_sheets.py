"""Syncs triage results to a Google Sheet, so a small business can see every
callable/blocked/needs-decision item next to CRM tooling many of them
already use, instead of a bespoke on-disk JSON log only Callismatic itself
can read.

Needs a Google Cloud service account JSON key file (path via
GOOGLE_SERVICE_ACCOUNT_FILE) and a target spreadsheet ID (GOOGLE_SHEET_ID).
The sheet must be shared with the service account's own email address
(found in the JSON key file, field `client_email`) with Editor access -- a
service account has no access to a sheet just because it exists in the same
Google account that created the key.

This connector is strictly opt-in: nothing in the core triage pipeline
calls it unless GOOGLE_SHEET_ID is actually set (see triage.py), so a
deployment with no Google credentials configured behaves exactly as it did
before this module existed.
"""

from __future__ import annotations

import os

from callismatic.schema import CallTriage

SHEET_RANGE = "Sheet1!A1"


def _sheets_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    key_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    if not key_file:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_FILE is not set -- see README.md for setup.")
    credentials = service_account.Credentials.from_service_account_file(
        key_file, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return build("sheets", "v4", credentials=credentials)


def sync_lead_to_sheet(
    triaged_at: str,
    source_name: str,
    caller_number: str,
    triage: CallTriage,
    *,
    sheet_id: str | None = None,
) -> None:
    """Appends one triaged voicemail/message as a new row in the configured Google Sheet.

    Raises RuntimeError if GOOGLE_SHEET_ID/GOOGLE_SERVICE_ACCOUNT_FILE are missing, or
    propagates the Sheets API's own error on failure -- callers that want CRM sync to be
    best-effort (see triage.py) are responsible for catching this.
    """
    sheet_id = sheet_id or os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise RuntimeError("GOOGLE_SHEET_ID is not set -- see README.md for setup.")

    service = _sheets_service()
    row = [
        triaged_at,
        source_name,
        caller_number,
        triage.category,
        triage.summary,
        str(triage.needs_decision),
        str(triage.callback_recommended),
        str(triage.block_recommended),
    ]
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=SHEET_RANGE,
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()
