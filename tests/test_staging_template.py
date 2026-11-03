"""The staging template's safety promises: it cannot spend CALL-E quota, cannot
publish to the production STILL bus, and cannot run a production image."""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATE = (Path(__file__).resolve().parents[1] / "template.yaml").read_text(encoding="utf-8")


def _code_lines() -> str:
    return "\n".join(line for line in TEMPLATE.splitlines() if not line.lstrip().startswith("#"))


def test_no_call_or_sms_provider_credentials_are_configured():
    variables = _code_lines().split("Variables:")[1].split("Policies:")[0]
    for name in ("CALLE_API_KEY", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "WHATSAPP_ACCESS_TOKEN"):
        assert name not in variables
    assert "GenerateStringKey: ADMIN_API_KEY" in TEMPLATE


def test_bus_parameter_only_accepts_the_staging_bus():
    pattern = re.search(r'AllowedPattern: "(\^arn:aws:events.+?)"', TEMPLATE).group(1).replace("\\\\", "\\")
    assert re.match(pattern, "arn:aws:events:ap-southeast-2:227214487086:event-bus/still-staging")
    assert not re.match(pattern, "arn:aws:events:ap-southeast-2:227214487086:event-bus/still")


def test_image_parameter_only_accepts_a_staging_tag():
    assert 'AllowedPattern: "^.+:staging$"' in TEMPLATE
    assert "callismatic:staging" in TEMPLATE
    assert "callismatic:latest" not in TEMPLATE


def test_no_wildcard_iam_resources_or_em_dashes():
    assert not re.search(r"(Resource|Action):\s*['\"]?\*", TEMPLATE)
    assert "—" not in TEMPLATE
