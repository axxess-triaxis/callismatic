from unittest.mock import MagicMock, patch

import pytest

from callismatic.todoist_sync import create_todoist_task


def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="TODOIST_API_TOKEN"):
        create_todoist_task("Call back the lead.")


def test_creates_task_with_correct_payload(monkeypatch):
    monkeypatch.setenv("TODOIST_API_TOKEN", "test-token")

    fake_response = MagicMock()
    fake_response.json.return_value = {"id": "123", "content": "Call back the lead."}
    fake_response.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=fake_response) as mock_post:
        result = create_todoist_task("Call back the lead.", due_string="tomorrow")

    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.todoist.com/rest/v2/tasks"
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"
    assert kwargs["json"]["content"] == "Call back the lead."
    assert kwargs["json"]["due_string"] == "tomorrow"
    assert result["id"] == "123"
