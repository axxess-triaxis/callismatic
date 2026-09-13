from unittest.mock import MagicMock, patch

import pytest

from callismatic.crm_sheets import sync_lead_to_sheet
from callismatic.schema import CallTriage


def test_missing_sheet_id_raises(monkeypatch):
    monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)
    triage = CallTriage(category="lead", summary="A new lead.", needs_decision=False)

    with pytest.raises(RuntimeError, match="GOOGLE_SHEET_ID"):
        sync_lead_to_sheet("2026-09-13T00:00:00Z", "lead.wav", "+15550001111", triage)


def test_sync_appends_expected_row(monkeypatch):
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet-123")
    triage = CallTriage(
        category="lead",
        summary="Kitchen remodel inquiry.",
        needs_decision=True,
        callback_recommended=False,
        block_recommended=False,
    )

    fake_append = MagicMock()
    fake_service = MagicMock()
    fake_service.spreadsheets.return_value.values.return_value.append.return_value = fake_append

    with patch("callismatic.crm_sheets._sheets_service", return_value=fake_service):
        sync_lead_to_sheet("2026-09-13T00:00:00Z", "lead.wav", "+15550002222", triage)

    _, kwargs = fake_service.spreadsheets.return_value.values.return_value.append.call_args
    assert kwargs["spreadsheetId"] == "sheet-123"
    row = kwargs["body"]["values"][0]
    assert row == [
        "2026-09-13T00:00:00Z",
        "lead.wav",
        "+15550002222",
        "lead",
        "Kitchen remodel inquiry.",
        "True",
        "False",
        "False",
    ]
    fake_append.execute.assert_called_once()
