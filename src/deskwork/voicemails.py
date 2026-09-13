"""Turns a voicemail recording into a plain-text transcript the agent can reason about.

Transcription itself is real AssemblyAI, not simulated -- the only synthetic
part of this whole pipeline is the sample *input* audio used for the demo
(see demo/generate_samples.py), never the transcription step.
"""

from __future__ import annotations

import os
from pathlib import Path

import assemblyai as aai

_configured = False


def _ensure_configured() -> None:
    global _configured
    if _configured:
        return
    api_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not api_key:
        raise RuntimeError("ASSEMBLYAI_API_KEY is not set -- see .env.example.")
    aai.settings.api_key = api_key
    _configured = True


def transcribe_voicemail(path: str | Path) -> str:
    """Returns the transcript text of a voicemail recording.

    Raises RuntimeError if ASSEMBLYAI_API_KEY is missing, or if AssemblyAI
    itself fails to transcribe the file, rather than silently returning
    empty text -- an empty read should never be confused with an empty
    voicemail.
    """
    _ensure_configured()
    path = Path(path)
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(str(path))
    if transcript.status == aai.TranscriptStatus.error:
        raise RuntimeError(f"AssemblyAI failed to transcribe {path.name}: {transcript.error}")
    return transcript.text or ""
