import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from callismatic.schema import CallTriage
from callismatic.triage import caller_number_from_filename, triage_inbox_concurrent, triage_text_message


def test_extracts_phone_number_from_filename():
    assert caller_number_from_filename(Path("scam_gift_card_+15550001111.wav")) == "+15550001111"


def test_missing_phone_number_returns_unknown():
    assert caller_number_from_filename(Path("no_number_here.wav")) == "unknown"


def test_triage_text_message_routes_through_shared_pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr("callismatic.tools.DIGEST_PATH", tmp_path / "digest.json")
    monkeypatch.setattr("callismatic.tools.BLOCKLIST_PATH", tmp_path / "blocklist.json")

    fake_route_call = MagicMock(return_value={"status": "completed"})
    monkeypatch.setattr("callismatic.triage.route_call", fake_route_call)

    triage = CallTriage(
        category="routine",
        summary="Confirming a delivery window.",
        needs_decision=False,
        callback_recommended=True,
        callback_task="Call back to confirm the delivery window.",
    )
    fake_agent = MagicMock()
    fake_agent.return_value.structured_output = triage

    result = triage_text_message(
        fake_agent, "whatsapp", "+15550001111", "msg-1", "Please call back to confirm delivery."
    )

    assert result.file_name == "whatsapp:msg-1"
    assert result.caller_number == "+15550001111"
    fake_route_call.assert_called_once_with("Call back to confirm the delivery window.", "+15550001111")
    assert result.callback_result == {"status": "completed"}


def test_triage_text_message_survives_callback_provider_failure(tmp_path, monkeypatch):
    # Real regression: CALL-E's API rejected a vague callback_task ("Confirm the 2:30 PM
    # cleaning appointment" -- no patient/booking name) with a CalleAPIError, and that
    # exception propagated straight out of route_call and crashed the whole batch run
    # instead of degrading just this one voicemail's result -- the same boundary
    # discipline carrier_intel.check_carrier_intel already follows ("never raises").
    monkeypatch.setattr("callismatic.tools.DIGEST_PATH", tmp_path / "digest.json")
    monkeypatch.setattr("callismatic.tools.BLOCKLIST_PATH", tmp_path / "blocklist.json")

    fake_route_call = MagicMock(side_effect=RuntimeError("Call task creation was rejected: ..."))
    monkeypatch.setattr("callismatic.triage.route_call", fake_route_call)

    triage = CallTriage(
        category="routine",
        summary="Confirming a cleaning appointment.",
        needs_decision=False,
        callback_recommended=True,
        callback_task="Confirm the 2:30 PM cleaning appointment.",
    )
    fake_agent = MagicMock()
    fake_agent.return_value.structured_output = triage

    result = triage_text_message(
        fake_agent, "sms", "+15550003333", "msg-3", "This is Lakeside Dental confirming your appointment."
    )

    assert result.error is None
    assert result.callback_result == {"status": "provider_error", "error": "Call task creation was rejected: ..."}


def test_triage_text_message_distinguishes_real_calle_failed_status_from_provider_error(tmp_path, monkeypatch):
    # CALL-E's own wait_for_result can legitimately return status="failed" for a call that
    # was genuinely created and attempted but never connected (no answer, unreachable number
    # -- exactly what happens calling this project's fictional +1555 sample numbers). That is
    # a real CALL-E result, not an exception, and must stay distinguishable from
    # "provider_error" (never even reached CALL-E with a valid request) -- the fix above must
    # not make a real CALL-E failure collide with route_call raising.
    monkeypatch.setattr("callismatic.tools.DIGEST_PATH", tmp_path / "digest.json")
    monkeypatch.setattr("callismatic.tools.BLOCKLIST_PATH", tmp_path / "blocklist.json")

    fake_route_call = MagicMock(return_value={"status": "failed", "call_id": "call_123"})
    monkeypatch.setattr("callismatic.triage.route_call", fake_route_call)

    triage = CallTriage(
        category="lead",
        summary="Kitchen remodel inquiry.",
        needs_decision=False,
        callback_recommended=True,
        callback_task="Call Daniel Ortiz back about the kitchen remodel.",
    )
    fake_agent = MagicMock()
    fake_agent.return_value.structured_output = triage

    result = triage_text_message(fake_agent, "sms", "+15550002222", "msg-4", "Kitchen remodel inquiry.")

    assert result.callback_result == {"status": "failed", "call_id": "call_123"}
    assert result.callback_result.get("status") != "provider_error"


def test_triage_text_message_skips_callback_when_not_recommended(tmp_path, monkeypatch):
    monkeypatch.setattr("callismatic.tools.DIGEST_PATH", tmp_path / "digest.json")
    monkeypatch.setattr("callismatic.tools.BLOCKLIST_PATH", tmp_path / "blocklist.json")

    fake_route_call = MagicMock()
    monkeypatch.setattr("callismatic.triage.route_call", fake_route_call)

    triage = CallTriage(
        category="important",
        summary="A client dispute needing a human.",
        needs_decision=True,
        callback_recommended=False,
    )
    fake_agent = MagicMock()
    fake_agent.return_value.structured_output = triage

    result = triage_text_message(fake_agent, "sms", "+15550002222", "msg-2", "We need to talk about the contract.")

    fake_route_call.assert_not_called()
    assert result.callback_result is None
    assert result.triage.needs_decision is True


def test_crm_sync_failure_does_not_break_triage(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("callismatic.tools.DIGEST_PATH", tmp_path / "digest.json")
    monkeypatch.setattr("callismatic.tools.BLOCKLIST_PATH", tmp_path / "blocklist.json")
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet-123")
    monkeypatch.setattr(
        "callismatic.crm_sheets.sync_lead_to_sheet",
        MagicMock(side_effect=RuntimeError("Sheets API is down")),
    )

    triage = CallTriage(category="routine", summary="Nothing urgent.", needs_decision=False)
    fake_agent = MagicMock()
    fake_agent.return_value.structured_output = triage

    result = triage_text_message(fake_agent, "sms", "+15550003333", "msg-3", "Just checking in.")

    assert result.error is None
    assert "CRM sync" in capsys.readouterr().err


def test_triage_inbox_concurrent_spawns_one_fresh_agent_per_voicemail(tmp_path, monkeypatch):
    monkeypatch.setattr("callismatic.tools.DIGEST_PATH", tmp_path / "digest.json")
    monkeypatch.setattr("callismatic.tools.BLOCKLIST_PATH", tmp_path / "blocklist.json")

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a_+15550001111.wav").write_bytes(b"fake")
    (inbox / "b_+15550002222.wav").write_bytes(b"fake")

    monkeypatch.setattr("callismatic.triage.transcribe_voicemail", lambda path: f"transcript for {path.name}")

    built_agents = []

    def fake_build_agent():
        fake_agent = MagicMock()
        fake_response = MagicMock()
        fake_response.structured_output = CallTriage(category="routine", summary="ok", needs_decision=False)
        fake_agent.invoke_async = AsyncMock(return_value=fake_response)
        built_agents.append(fake_agent)
        return fake_agent

    monkeypatch.setattr("callismatic.triage.build_agent", fake_build_agent)

    results = asyncio.run(triage_inbox_concurrent(inbox, place_callbacks=False))

    assert len(results) == 2
    assert len(built_agents) == 2, "each voicemail must get its own sub-agent, never a shared one"
    assert {r.file_name for r in results} == {"a_+15550001111.wav", "b_+15550002222.wav"}
    for fake_agent in built_agents:
        fake_agent.invoke_async.assert_awaited_once()


def test_triage_inbox_concurrent_respects_max_concurrency(tmp_path, monkeypatch):
    monkeypatch.setattr("callismatic.tools.DIGEST_PATH", tmp_path / "digest.json")
    monkeypatch.setattr("callismatic.tools.BLOCKLIST_PATH", tmp_path / "blocklist.json")

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for i in range(6):
        (inbox / f"v{i}_+1555000000{i}.wav").write_bytes(b"fake")

    monkeypatch.setattr("callismatic.triage.transcribe_voicemail", lambda path: "transcript")

    in_flight = 0
    peak = 0
    lock = asyncio.Lock()

    async def fake_invoke_async(prompt, structured_output_model=None):
        nonlocal in_flight, peak
        async with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        async with lock:
            in_flight -= 1
        response = MagicMock()
        response.structured_output = CallTriage(category="routine", summary="ok", needs_decision=False)
        return response

    def fake_build_agent():
        fake_agent = MagicMock()
        fake_agent.invoke_async = fake_invoke_async
        return fake_agent

    monkeypatch.setattr("callismatic.triage.build_agent", fake_build_agent)

    results = asyncio.run(triage_inbox_concurrent(inbox, place_callbacks=False, max_concurrency=2))

    assert len(results) == 6
    assert peak <= 2, f"expected at most 2 sub-agents in flight at once, saw {peak}"
