from callismatic.auth import is_admin, is_reader, key_from_headers, key_matches


def test_key_matches_fails_closed_on_missing_values():
    assert not key_matches(None, "k")
    assert not key_matches("k", None)
    assert not key_matches("", "")
    assert key_matches("k", "k")
    assert not key_matches("k", "K")


def test_reader_and_admin_keys(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin")
    monkeypatch.setenv("READ_API_KEY", "reader")
    assert is_admin("admin") and is_reader("admin")
    assert is_reader("reader") and not is_admin("reader")
    assert not is_reader("nope")


def test_no_keys_configured_means_nobody_gets_in(monkeypatch):
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    monkeypatch.delenv("READ_API_KEY", raising=False)
    assert not is_admin("") and not is_reader("") and not is_reader(None)


def test_key_from_headers():
    assert key_from_headers({"x-api-key": "a"}) == "a"
    assert key_from_headers({"authorization": "Bearer b"}) == "b"
    assert key_from_headers({"authorization": "bearer  c "}) == "c"
    assert key_from_headers({"authorization": "Basic d"}) is None
    assert key_from_headers({}) is None
