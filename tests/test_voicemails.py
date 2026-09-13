from unittest.mock import MagicMock, patch

import assemblyai as aai
import pytest

from deskwork import voicemails


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("ASSEMBLYAI_API_KEY", raising=False)
    voicemails._configured = False
    with pytest.raises(RuntimeError, match="ASSEMBLYAI_API_KEY"):
        voicemails.transcribe_voicemail("does-not-matter.wav")


def test_transcribe_returns_text(monkeypatch, tmp_path):
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "test-key")
    voicemails._configured = False
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"fake-audio")

    fake_transcript = MagicMock()
    fake_transcript.status = aai.TranscriptStatus.completed
    fake_transcript.text = "Hello, this is a test voicemail."

    with patch("deskwork.voicemails.aai.Transcriber") as mock_transcriber_cls:
        mock_transcriber_cls.return_value.transcribe.return_value = fake_transcript
        text = voicemails.transcribe_voicemail(audio)

    assert text == "Hello, this is a test voicemail."


def test_transcription_error_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "test-key")
    voicemails._configured = False
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"fake-audio")

    fake_transcript = MagicMock()
    fake_transcript.status = aai.TranscriptStatus.error
    fake_transcript.error = "unsupported format"

    with patch("deskwork.voicemails.aai.Transcriber") as mock_transcriber_cls:
        mock_transcriber_cls.return_value.transcribe.return_value = fake_transcript
        with pytest.raises(RuntimeError, match="unsupported format"):
            voicemails.transcribe_voicemail(audio)
