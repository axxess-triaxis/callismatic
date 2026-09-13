from unittest.mock import MagicMock

from callismatic import call_router


def test_country_code_for_india_number():
    assert call_router.country_code_for("+918402999963") == 91


def test_country_code_for_us_number():
    assert call_router.country_code_for("+15551234567") == 1


def test_country_code_for_unparseable_number():
    assert call_router.country_code_for("not-a-number") is None


def test_route_call_falls_back_to_default_provider(monkeypatch):
    fake_default = MagicMock(return_value={"status": "completed"})
    monkeypatch.setattr(call_router, "DEFAULT_PROVIDER", fake_default)
    monkeypatch.setattr(call_router, "PROVIDERS_BY_COUNTRY_CODE", {})

    result = call_router.route_call("Call back and confirm.", "+15551234567")

    fake_default.assert_called_once_with("Call back and confirm.", "+15551234567")
    assert result["status"] == "completed"


def test_route_call_uses_registered_country_provider(monkeypatch):
    fake_india_provider = MagicMock(return_value={"status": "completed", "via": "india-local"})
    fake_default = MagicMock(return_value={"status": "completed", "via": "default"})
    monkeypatch.setattr(call_router, "PROVIDERS_BY_COUNTRY_CODE", {91: fake_india_provider})
    monkeypatch.setattr(call_router, "DEFAULT_PROVIDER", fake_default)

    result = call_router.route_call("Call back and confirm.", "+918402999963")

    fake_india_provider.assert_called_once_with("Call back and confirm.", "+918402999963")
    fake_default.assert_not_called()
    assert result["via"] == "india-local"
