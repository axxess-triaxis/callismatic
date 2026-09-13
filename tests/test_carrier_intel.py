from unittest.mock import MagicMock, patch

from callismatic.carrier_intel import check_carrier_intel


def test_missing_credentials_returns_note(monkeypatch):
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)

    report = check_carrier_intel("+15550001111")

    assert "unavailable" in report.lower()
    assert "TWILIO_ACCOUNT_SID" in report


def test_successful_lookup_reports_line_type(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test_token")

    fake_lookup = MagicMock()
    fake_lookup.line_type_intelligence = {"type": "voip", "carrier_name": "Example VOIP Co"}

    fake_client = MagicMock()
    fake_client.lookups.v2.phone_numbers.return_value.fetch.return_value = fake_lookup

    with patch("twilio.rest.Client", return_value=fake_client):
        report = check_carrier_intel("+15550001111")

    assert "voip" in report.lower()
    assert "Example VOIP Co" in report


def test_embedded_error_code_is_reported_distinctly(monkeypatch):
    """Twilio can return HTTP 200 with an error_code embedded inside
    line_type_intelligence itself (e.g. 60627 for a trial-account quota
    limit) -- confirmed against the real API this session. This must be
    reported as a diagnosable Twilio-side condition, not silently shown as
    an empty/unknown line type."""
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test_token")

    fake_lookup = MagicMock()
    fake_lookup.line_type_intelligence = {
        "carrier_name": None,
        "error_code": 60627,
        "mobile_country_code": None,
        "mobile_network_code": None,
        "type": None,
    }

    fake_client = MagicMock()
    fake_client.lookups.v2.phone_numbers.return_value.fetch.return_value = fake_lookup

    with patch("twilio.rest.Client", return_value=fake_client):
        report = check_carrier_intel("+918402999963")

    assert "60627" in report
    assert "unavailable" in report.lower()


def test_lookup_failure_is_reported_not_raised(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test_token")

    from twilio.base.exceptions import TwilioRestException

    fake_client = MagicMock()
    fake_client.lookups.v2.phone_numbers.return_value.fetch.side_effect = TwilioRestException(
        status=404, uri="/lookup", msg="not found"
    )

    with patch("twilio.rest.Client", return_value=fake_client):
        report = check_carrier_intel("+15550001111")

    assert "failed" in report.lower()
