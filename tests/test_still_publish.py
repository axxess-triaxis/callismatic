import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import jsonschema
import pytest

from callismatic import still_emit
from callismatic.schema import CallTriage
from callismatic.triage import still_event_data, triage_text_message

BUS = "arn:aws:events:ap-southeast-2:123456789012:event-bus/still"
SCHEMA = json.loads((Path(__file__).parent / "fixtures" / "still_lead.triaged.v1.json").read_text(encoding="utf-8"))


class FakeEvents:
    def __init__(self, error=None):
        self.entries = []
        self.error = error

    def put_events(self, Entries):
        if self.error:
            raise self.error
        self.entries.extend(Entries)
        return {"FailedEntryCount": 0, "Entries": [{"EventId": "e"}]}


def lead():
    return CallTriage(
        category="lead",
        summary="Daniel wants a kitchen remodel quote.",
        key_facts={"name": "Daniel"},
        needs_decision=True,
        decision_reason="New client inquiry.",
        suggested_action="Call Daniel back about the quote.",
        urgency="medium",
    )


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr("callismatic.tools.DIGEST_PATH", tmp_path / "digest.json")
    monkeypatch.setattr("callismatic.tools.BLOCKLIST_PATH", tmp_path / "blocklist.json")
    monkeypatch.setattr("callismatic.todos.TODOS_PATH", tmp_path / "todos.json", raising=False)
    monkeypatch.setattr("callismatic.triage.route_call", MagicMock())
    events = FakeEvents()
    real_emit = still_emit.emit
    monkeypatch.setattr(still_emit, "emit", lambda *a, **k: real_emit(*a, client=events, **k))
    agent = MagicMock()
    agent.return_value.structured_output = lead()
    return agent, events


@pytest.mark.parametrize("source, channel, caller, expected_caller", [
    ("sms:abc", "sms", "+15550001111", "+15550001111"),
    ("whatsapp:wamid.1", "whatsapp", "+15550001111", "+15550001111"),
    ("new_lead_+15550001111.wav", "voicemail", "unknown", None),
])
def test_event_data_matches_still_schema(source, channel, caller, expected_caller):
    data = still_event_data(source, caller, lead())
    jsonschema.validate(data, SCHEMA)
    assert data["channel"] == channel
    assert data["caller_number"] == expected_caller
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z", data["triaged_at"])


def test_nothing_is_published_unless_still_is_configured(pipeline, monkeypatch):
    agent, events = pipeline
    monkeypatch.delenv(still_emit.BUS_ENV, raising=False)
    triage_text_message(agent, "sms", "+15550001111", "m1", "Hi, I'd like a quote.", place_callbacks=False)
    assert events.entries == []


def test_triage_publishes_one_event_keyed_on_the_item(pipeline, monkeypatch):
    agent, events = pipeline
    monkeypatch.setenv(still_emit.BUS_ENV, BUS)
    triage_text_message(agent, "sms", "+15550001111", "m1", "Hi, I'd like a quote.", place_callbacks=False)
    triage_text_message(agent, "sms", "+15550001111", "m1", "Hi, I'd like a quote.", place_callbacks=False)
    first, second = (json.loads(e["Detail"]) for e in events.entries)
    assert events.entries[0]["Source"] == "triaxis.callismatic"
    assert events.entries[0]["DetailType"] == "lead.triaged.v1"
    assert first["id"] == second["id"]
    assert first["data"]["source_ref"] == "sms:m1"
    jsonschema.validate(first["data"], SCHEMA)


def test_still_failure_never_breaks_triage(pipeline, monkeypatch, capsys):
    agent, events = pipeline
    monkeypatch.setenv(still_emit.BUS_ENV, BUS)
    events.error = RuntimeError("bus down, +15550001111")
    result = triage_text_message(agent, "sms", "+15550001111", "m1", "Hi", place_callbacks=False)
    assert result.triage.category == "lead"
    err = capsys.readouterr().err
    assert "STILL publish failed for sms:m1: RuntimeError" in err
    assert "+1555" not in err
