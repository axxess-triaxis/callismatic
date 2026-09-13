from unittest.mock import MagicMock, patch

import pytest

from callismatic.meeting_notes import MeetingNotes, summarize_call


def test_summarize_call_raises_on_empty_transcript():
    with pytest.raises(ValueError, match="no transcript_turns"):
        summarize_call("Confirm the appointment", [])


def test_summarize_call_returns_structured_notes():
    notes = MeetingNotes(
        summary="Confirmed the 2:30pm appointment.",
        key_points=["Appointment confirmed for 2:30pm"],
        action_items=[],
        follow_up_needed=False,
    )
    fake_response = MagicMock()
    fake_response.structured_output = notes
    fake_agent = MagicMock(return_value=fake_response)

    with patch("callismatic.meeting_notes.Agent", return_value=fake_agent):
        result = summarize_call(
            "Confirm the appointment",
            [{"speaker": "agent", "text": "Can you confirm 2:30pm?"}, {"speaker": "caller", "text": "Yes."}],
        )

    assert result.summary == "Confirmed the 2:30pm appointment."
    assert result.follow_up_needed is False
    fake_agent.assert_called_once()
