"""Test-wide isolation from the developer's real .env.

cli.main() and whatsapp_webhook (at import time) call load_dotenv(), which copies the real .env --
AWS profile, API keys, WhatsApp/Twilio tokens -- into os.environ for every test that runs after
it. On CI there is no .env, so tests passed there and failed (or worse, reached real services)
locally depending on test order. conftest.py is imported before any test module, so replacing
dotenv.load_dotenv here also covers the `from dotenv import load_dotenv` bindings in src/.
"""

import dotenv
import pytest


def _no_dotenv(*args, **kwargs):
    return False


dotenv.load_dotenv = _no_dotenv


@pytest.fixture(autouse=True)
def no_real_aws_config(monkeypatch, tmp_path):
    """Keep boto3 away from the developer's ~/.aws: building a BedrockModel resolves
    credentials, and a real profile (e.g. an `aws login` session) must never decide whether
    a test passes or reach real AWS."""
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "aws-config-absent"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "aws-credentials-absent"))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
