import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from callismatic import outbound, web
from callismatic.outbound import (
    CallReport,
    OutboundCallRequest,
    ProviderUnavailable,
    build_task,
    dispatch_outbound_job,
    provider_for,
    run_outbound_job,
)

JOB = "11111111-2222-3333-4444-555555555555"
LEAD = "22222222-3333-4444-5555-666666666666"
ORG = "33333333-4444-5555-6666-777777777777"
PHONE = "+919876543210"
BODY = {"job_id": JOB, "lead_id": LEAD, "organization_id": ORG, "phone_e164": PHONE, "country": "IN",
        "title": "Acme - Asha", "contact_name": "Asha", "company": "Acme"}
SLOT = (datetime(2026, 11, 17, 5, 30, tzinfo=timezone.utc), datetime(2026, 11, 17, 6, 0, tzinfo=timezone.utc))


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("OUTBOUND_AGENT_CALLS_ENABLED", "OUTBOUND_FAKE_PROVIDER", "CALLISMATIC_STAGE", "AWS_LAMBDA_FUNCTION_NAME", "READ_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")


def _post(body=BODY, key="test-admin-key"):
    return TestClient(web.app).post("/api/outbound-calls", json=body, headers={"X-API-Key": key} if key else {})


def _request(**over):
    return OutboundCallRequest.model_validate({**BODY, **over})


# --- the endpoint -----------------------------------------------------------------------------


def test_needs_the_admin_key():
    assert _post(key=None).status_code == 401
    assert _post(key="wrong").status_code == 401


def test_is_off_by_default():
    response = _post()
    assert response.status_code == 503
    assert response.json() == {"error": "outbound_disabled"}


def test_refuses_india_with_no_lead_call_provider_and_never_falls_back_to_calle(monkeypatch):
    monkeypatch.setenv("OUTBOUND_AGENT_CALLS_ENABLED", "true")
    dispatched = MagicMock()
    monkeypatch.setattr(web, "dispatch_outbound_job", dispatched)
    response = _post()
    assert response.status_code == 409
    assert response.json() == {"error": "provider_unavailable"}
    dispatched.assert_not_called()


def test_accepts_and_dispatches_on_staging_with_the_fake_provider(monkeypatch):
    monkeypatch.setenv("OUTBOUND_AGENT_CALLS_ENABLED", "true")
    monkeypatch.setenv("OUTBOUND_FAKE_PROVIDER", "true")
    monkeypatch.setenv("CALLISMATIC_STAGE", "staging")
    dispatched = MagicMock()
    monkeypatch.setattr(web, "dispatch_outbound_job", dispatched)
    response = _post()
    assert response.status_code == 202
    assert response.json() == {"accepted": True}
    assert dispatched.call_args.args[0].job_id == JOB


def test_rejects_a_malformed_job(monkeypatch):
    monkeypatch.setenv("OUTBOUND_AGENT_CALLS_ENABLED", "true")
    assert _post({**BODY, "country": "US"}).status_code == 422
    assert _post({**BODY, "phone_e164": "98765"}).status_code == 422
    assert _post({**BODY, "job_id": "not-a-uuid"}).status_code == 422


def test_the_fake_provider_never_runs_outside_staging(monkeypatch):
    monkeypatch.setenv("OUTBOUND_FAKE_PROVIDER", "true")
    with pytest.raises(ProviderUnavailable):
        provider_for(PHONE)
    monkeypatch.setenv("CALLISMATIC_STAGE", "production")
    with pytest.raises(ProviderUnavailable):
        provider_for(PHONE)


def test_a_registered_provider_is_used(monkeypatch):
    provider = MagicMock()
    monkeypatch.setitem(outbound.OUTBOUND_PROVIDERS_BY_COUNTRY_CODE, 91, provider)
    assert provider_for(PHONE) is provider


# --- the call task ----------------------------------------------------------------------------


def test_the_task_discloses_the_ai_offers_slots_in_local_time_and_honours_opt_out():
    task = build_task(_request(), [SLOT])
    assert "you are an AI assistant calling on behalf of Triaxis Ventures" in task
    assert "not be called again" in task
    assert "Asia/Kolkata" in task and "11:00 AM" in task  # 05:30 UTC is 11:00 IST
    assert PHONE not in task
    assert "ask which weekday and time" in build_task(_request(), [])


# --- running a job ------------------------------------------------------------------------------


def _run(report=None, turns=True, provider=None, emitted=None):
    emitted = [] if emitted is None else emitted
    place = provider or (lambda task, phone: {"transcript_turns": [{"speaker": "contact", "text": "yes"}] if turns else []})
    classify = MagicMock(return_value=report)
    data = run_outbound_job(
        _request(), provider=place, classify=classify, slots_fn=lambda country: [SLOT],
        emit_fn=lambda source, event_type, data, **kw: emitted.append((source, event_type, data, kw)),
    )
    return data, emitted, classify


def test_an_interested_call_reports_the_accepted_slot_and_no_transcript_or_phone():
    report = CallReport(outcome="interested", summary="Wants a demo.", action_items=["Send deck"], accepted_slot_start="2026-11-17T05:30:00Z")
    data, emitted, _ = _run(report)
    assert data["status"] == "completed"
    assert data["outcome"] == "interested"
    assert data["accepted_slot"] == {"starts_at": SLOT[0].isoformat(), "ends_at": SLOT[1].isoformat()}
    source, event_type, event, kw = emitted[0]
    assert (source, event_type, kw["key"]) == ("triaxis.callismatic", "call.completed.v1", JOB)
    serialized = json.dumps(event)
    assert PHONE not in serialized and "transcript" not in serialized
    assert event["title"] == "Acme - Asha"


def test_a_slot_that_was_not_offered_is_dropped():
    report = CallReport(outcome="interested", summary="", accepted_slot_start="2026-12-01T05:30:00Z")
    data, _, _ = _run(report)
    assert data["accepted_slot"] is None


def test_an_opt_out_becomes_not_interested_with_no_slot_or_follow_up():
    report = CallReport(outcome="interested", summary="Asked not to be called.", accepted_slot_start="2026-11-17T05:30:00Z",
                        follow_up_at="2026-11-20T05:30:00Z", opted_out=True)
    data, _, _ = _run(report)
    assert (data["outcome"], data["accepted_slot"], data["follow_up_at"], data["opted_out"]) == ("not_interested", None, None, True)


def test_no_conversation_is_a_no_answer_without_asking_the_model():
    data, _, classify = _run(turns=False)
    assert data["outcome"] == "no_answer"
    classify.assert_not_called()


def test_a_failing_provider_still_reports_back():
    def broken(task, phone):
        raise RuntimeError("boom")

    data, emitted, _ = _run(provider=broken)
    assert (data["status"], data["failure_reason"]) == ("failed", "call_error")
    assert emitted


def test_no_provider_reports_provider_unavailable():
    emitted = []
    data = run_outbound_job(_request(), slots_fn=lambda c: [], emit_fn=lambda *a, **k: emitted.append(a))
    assert (data["status"], data["failure_reason"]) == ("failed", "provider_unavailable")
    assert emitted


# --- dispatch -----------------------------------------------------------------------------------


def test_on_lambda_the_job_is_an_async_self_invoke(monkeypatch):
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "callismatic")
    client = MagicMock()
    dispatch_outbound_job(_request(), lambda_client=client)
    kwargs = client.invoke.call_args.kwargs
    assert kwargs["FunctionName"] == "callismatic"
    assert kwargs["InvocationType"] == "Event"
    assert json.loads(kwargs["Payload"])["callismatic_outbound_job"]["job_id"] == JOB
