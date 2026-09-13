import pytest
from pydantic import ValidationError

from deskwork.schema import DocumentTriage


def test_minimal_valid_triage():
    triage = DocumentTriage(
        doc_type="invoice",
        summary="An unpaid invoice for office supplies.",
        needs_decision=True,
        decision_reason="Payment is overdue.",
        suggested_action="Pay the invoice or contact the vendor.",
        deadline="2026-08-28",
        urgency="high",
    )
    assert triage.needs_decision is True
    assert triage.key_facts == {}


def test_invalid_doc_type_rejected():
    with pytest.raises(ValidationError):
        DocumentTriage(doc_type="spreadsheet", summary="x", needs_decision=False)
