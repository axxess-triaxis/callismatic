"""The one structured shape every triaged document is forced into.

Keeping this a flat, required-field schema (rather than a looser dict) is
what makes the "only surface real decisions" behavior mechanical instead of
a matter of prompt-reading: the CLI never re-interprets the model's prose,
it just checks `needs_decision`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DocType = Literal["invoice", "contract", "form", "correspondence", "newsletter", "other"]
Urgency = Literal["none", "low", "medium", "high"]


class DocumentTriage(BaseModel):
    doc_type: DocType = Field(description="What kind of document this is")
    summary: str = Field(description="One or two sentence plain-language summary")
    key_facts: dict[str, str] = Field(
        default_factory=dict,
        description="The concrete facts worth remembering, e.g. amount, sender, deadline -- "
        "keys and values as short strings, only the facts actually present in the document",
    )
    needs_decision: bool = Field(
        description="True only if a human must actually decide or act on something -- "
        "an FYI, a receipt, or a newsletter is false even if it's informative"
    )
    decision_reason: str | None = Field(
        default=None,
        description="If needs_decision is true, the one sentence reason a human has to weigh in",
    )
    suggested_action: str | None = Field(
        default=None,
        description="If needs_decision is true, the concrete next step to take",
    )
    deadline: str | None = Field(
        default=None,
        description="ISO date (YYYY-MM-DD) if the document implies one, else null",
    )
    urgency: Urgency = Field(
        default="none",
        description="How time-sensitive this is; 'none' unless needs_decision is true",
    )
