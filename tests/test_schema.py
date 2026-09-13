import pytest
from pydantic import ValidationError

from deskwork.schema import CallTriage


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
