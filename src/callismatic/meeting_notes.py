"""Turns a completed CALL-E call's transcript into structured meeting notes.

This is the natural home for "AI note-taker": every callback Callismatic
places already produces a real conversation transcript
(CALL-E's own `transcript_turns` in the call result). Rather than a
separate note-taking product, this summarizes that transcript into the
same kind of structured record a human assistant would hand you after a
call -- what was discussed, what was decided, what needs following up.

Reuses the same Bedrock model already configured for triage (models.get_model)
-- no new credentials needed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from strands import Agent

from callismatic.models import get_model

NOTES_SYSTEM_PROMPT = """You are a meeting note-taker. You are given the transcript of a \
phone call CALL-E just placed on someone's behalf. Produce a short, accurate record of what \
actually happened -- never invent a detail that wasn't in the transcript, and never soften an \
unresolved or awkward outcome into something tidier than it was."""


class MeetingNotes(BaseModel):
    summary: str = Field(description="One or two sentence plain-language summary of what happened on the call")
    key_points: list[str] = Field(
        default_factory=list, description="The concrete facts discussed -- names, dates, amounts, decisions"
    )
    action_items: list[str] = Field(
        default_factory=list, description="Concrete next steps that came out of the call, if any"
    )
    follow_up_needed: bool = Field(description="True if a human should review this call before considering it closed")


def _format_transcript(transcript_turns: list[dict]) -> str:
    lines = []
    for turn in transcript_turns:
        speaker = turn.get("speaker", turn.get("role", "unknown"))
        text = turn.get("text", turn.get("content", ""))
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


def summarize_call(task: str, transcript_turns: list[dict]) -> MeetingNotes:
    """Summarizes a completed CALL-E call into structured notes.

    Raises ValueError if transcript_turns is empty -- there is nothing to summarize from a
    call that never produced a real conversation (e.g. NO_ANSWER), and fabricating notes for
    a call that didn't happen would be worse than surfacing that plainly.
    """
    if not transcript_turns:
        raise ValueError("Cannot summarize a call with no transcript_turns -- it likely never connected.")

    agent = Agent(model=get_model(), system_prompt=NOTES_SYSTEM_PROMPT)
    prompt = f"The call's task was: {task}\n\nTranscript:\n{_format_transcript(transcript_turns)}"
    response = agent(prompt, structured_output_model=MeetingNotes)
    return response.structured_output
