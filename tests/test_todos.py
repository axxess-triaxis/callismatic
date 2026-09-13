from unittest.mock import MagicMock

from callismatic import todos


def test_add_and_list_todo(tmp_path, monkeypatch):
    monkeypatch.setattr(todos, "TODOS_PATH", tmp_path / "todos.json")
    monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)

    item = todos.add_todo("Call Priya back about the contract.")

    assert item["done"] is False
    assert todos.list_todos() == [item]


def test_add_todo_from_triage_records_source(tmp_path, monkeypatch):
    monkeypatch.setattr(todos, "TODOS_PATH", tmp_path / "todos.json")
    monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)

    item = todos.add_todo_from_triage("important_client.wav", "Call Priya back.")

    assert item["source"] == "important_client.wav"
    assert item["text"] == "Call Priya back."


def test_complete_todo_marks_done(tmp_path, monkeypatch):
    monkeypatch.setattr(todos, "TODOS_PATH", tmp_path / "todos.json")
    monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)

    item = todos.add_todo("Follow up.")
    completed = todos.complete_todo(item["id"])

    assert completed is True
    assert todos.list_todos() == []
    assert todos.list_todos(include_done=True)[0]["done"] is True


def test_complete_unknown_id_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(todos, "TODOS_PATH", tmp_path / "todos.json")
    assert todos.complete_todo("todo-999") is False


def test_todoist_sync_failure_does_not_break_add_todo(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(todos, "TODOS_PATH", tmp_path / "todos.json")
    monkeypatch.setenv("TODOIST_API_TOKEN", "test-token")
    monkeypatch.setattr(
        "callismatic.todoist_sync.create_todoist_task", MagicMock(side_effect=RuntimeError("Todoist is down"))
    )

    item = todos.add_todo("Call the lead back.")

    assert item is not None
    assert "Todoist sync failed" in capsys.readouterr().err
