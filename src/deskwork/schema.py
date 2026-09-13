"""The one structured shape every triaged voicemail is forced into.

Keeping this a flat, required-field schema (rather than a looser dict) is
what makes "only surface real decisions, only call back what's safe to
automate, only block what's actually a scam" mechanical instead of a matter
of prompt-reading: the CLI never re-interprets the model's prose, it just
checks the booleans.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CallCategory = Literal["scam", "spam", "lead", "important", "routine"]
Urgency = Literal["none", "low", "medium", "high"]


class CallTriage(BaseModel):
    category: CallCategory = Field(description="What kind of caller this voicemail is from")
    summary: str = Field(description="One or two sentence plain-language summary of the voicemail")
    key_facts: dict[str, str] = Field(
        default_factory=dict,
        description="The concrete facts worth remembering, e.g. caller name, company, request -- "
        "keys and values as short strings, only the facts actually present in the transcript",
    )
    needs_decision: bool = Field(
        description="True only if a human must personally decide or respond -- a resolved "
        "matter or a courtesy notice is false even if it's informative"
    )
    decision_reason: str | None = Field(
        default=None,
        description="If needs_decision is true, the one sentence reason a human has to weigh in",
    )
    suggested_action: str | None = Field(
        default=None,
        description="If needs_decision is true, the concrete next step to take",
    )
    callback_recommended: bool = Field(
        default=False,
        description="True only if the caller's request is simple and well-defined enough to "
        "complete automatically without a human deciding anything -- confirming an appointment, "
        "acknowledging receipt, giving a callback window",
    )
    callback_task: str | None = Field(
        default=None,
        description="If callback_recommended is true, the exact natural-language instruction "
        "for the calling agent to carry out, e.g. 'Call back and confirm the 2:30pm cleaning "
        "appointment.'",
    )
    block_recommended: bool = Field(
        default=False,
        description="True only if the transcript shows concrete scam/spam evidence -- never on "
        "vague suspicion alone",
    )
    urgency: Urgency = Field(
        default="none",
        description="How time-sensitive this is; 'none' unless needs_decision is true",
    )
