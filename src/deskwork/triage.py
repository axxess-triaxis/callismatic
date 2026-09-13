"""Scans an inbox folder and triages every document in it, one agent call
each. This is where "only surfaces when there's a real decision to make"
actually happens: everything the agent returns gets logged, but only the
needs_decision=true items are ever printed for the human to see."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from strands import Agent

from deskwork.documents import read_document_text
from deskwork.schema import DocumentTriage
from deskwork.tools import record_decision

SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md"}


@dataclass
class TriageResult:
    file_name: str
    triage: DocumentTriage
    error: str | None = None


def triage_inbox(agent: Agent, inbox_dir: Path) -> list[TriageResult]:
    results = []
    for path in sorted(inbox_dir.iterdir()):
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        results.append(_triage_one(agent, path))
    return results


def _triage_one(agent: Agent, path: Path) -> TriageResult:
    try:
        text = read_document_text(path)
    except ValueError as e:
        return TriageResult(file_name=path.name, triage=None, error=str(e))  # type: ignore[arg-type]

    prompt = f"Triage this document.\n\nFile name: {path.name}\n\nContent:\n{text}"
    response = agent(prompt, structured_output_model=DocumentTriage)
    triage: DocumentTriage = response.structured_output

    record_decision(path.name, triage.model_dump())
    return TriageResult(file_name=path.name, triage=triage)
