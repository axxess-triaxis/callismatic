import pytest
from pydantic import ValidationError

from callismatic.schema import CallTriage


def test_minimal_valid_triage():
    triage = CallTriage(
        category="scam",
        summary="Automated threat demanding a gift-card payment.",
        needs_decision=False,
        block_recommended=True,
        urgency="high",
    )
    assert triage.block_recommended is True
    assert triage.key_facts == {}


def test_callback_task_carried_when_recommended():
    triage = CallTriage(
        category="routine",
        summary="Dentist office confirming tomorrow's cleaning.",
        needs_decision=False,
        callback_recommended=True,
        callback_task="Call back and confirm the 2:30pm cleaning appointment.",
    )
    assert triage.callback_task == "Call back and confirm the 2:30pm cleaning appointment."


def test_invalid_category_rejected():
    with pytest.raises(ValidationError):
        CallTriage(category="telemarketer", summary="x", needs_decision=False)


def test_web_evidence_is_optional_so_existing_digest_entries_still_load():
    """Digest entries written before SerpApi web intel existed have no web_evidence key."""
    legacy = {"category": "lead", "summary": "New kitchen remodel lead.", "needs_decision": True}
    triage = CallTriage.model_validate(legacy)
    assert triage.web_evidence is None


def test_web_evidence_carried_when_set():
    triage = CallTriage(
        category="scam",
        summary="TRAI impersonation threatening disconnection.",
        needs_decision=False,
        block_recommended=True,
        web_evidence="CONTRADICTS: number listed on a scam-report site (tellows.com).",
    )
    assert "tellows.com" in triage.web_evidence
